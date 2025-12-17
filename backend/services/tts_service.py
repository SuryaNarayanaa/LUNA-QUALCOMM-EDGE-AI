import os
import json
import logging
import numpy as np
import torch
import librosa
from pydub import AudioSegment
from typing import Dict, List, Optional, Tuple
from TTS.api import TTS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VoiceCloningTTSService:
    """Voice cloning TTS service using xTTS for generating audio from edited transcripts"""
    
    def __init__(self, assets_dir: str = None):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tts_model = None
        self.speaker_voice_samples = {}
        
        # Set up paths - use absolute paths
        if assets_dir is None:
            # Get the backend directory (parent of services)
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.assets_dir = os.path.join(backend_dir, "assests")
        else:
            self.assets_dir = assets_dir
            
        self.original_audio_path = os.path.join(self.assets_dir, "audio", "extracted_audio.wav")
        self.speaker_audio_dir = os.path.join(self.assets_dir, "speaker_audio")
        self.transcripts_dir = os.path.join(self.assets_dir, "users_segements")
          # Also check the alternative speaker_audio location in backend root
        backend_dir = os.path.dirname(self.assets_dir)
        self.alt_speaker_audio_dir = os.path.join(backend_dir, "speaker_audio")
        
        self._initialize_xtts_model()
        self._load_speaker_voice_samples()
    
    def _initialize_xtts_model(self):
        """Initialize xTTS model for voice cloning"""
        try:
            # Load xTTS v2 model for multilingual voice cloning
            self.tts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(self.device)
            logger.info("xTTS model loaded successfully on device: %s", self.device)
        except Exception as e:
            logger.error(f"Failed to load xTTS model: {e}")
            # Don't raise the exception, just set tts_model to None for debugging
            self.tts_model = None
            logger.warning("TTS model initialization failed, continuing with None model for debugging")
    
    def _load_speaker_voice_samples(self):
        """Load existing speaker voice samples from speaker_audio directories"""
        try:
            # Check primary speaker audio directory
            directories_to_check = [self.speaker_audio_dir, self.alt_speaker_audio_dir]
            
            for speaker_dir in directories_to_check:
                if os.path.exists(speaker_dir):
                    logger.info(f"Loading speaker samples from: {speaker_dir}")
                    for file in os.listdir(speaker_dir):
                        if file.endswith('.wav'):
                            speaker_id = file.replace('.wav', '')
                            sample_path = os.path.join(speaker_dir, file)
                            self.speaker_voice_samples[speaker_id] = sample_path
                            logger.info(f"Loaded voice sample for {speaker_id}")
                    break  # Use the first directory that exists
            
            if not self.speaker_voice_samples:
                logger.warning(f"No speaker voice samples found in directories: {directories_to_check}")
                    
        except Exception as e:
            logger.error(f"Error loading speaker voice samples: {e}")
    
    def load_transcript_data(self, edited_transcript_path: str = None, original_transcript_path: str = None):
        """Load both edited and original transcript JSON files"""
        try:
            # Use default paths if not provided
            if not edited_transcript_path:
                edited_transcript_path = os.path.join(self.transcripts_dir, "transcript-edited.json")
            if not original_transcript_path:
                original_transcript_path = os.path.join(self.transcripts_dir, "transcript.json")
            
            with open(edited_transcript_path, 'r', encoding='utf-8') as f:
                edited_data = json.load(f)
            
            with open(original_transcript_path, 'r', encoding='utf-8') as f:
                original_data = json.load(f)
            
            logger.info(f"Loaded transcripts: {len(edited_data.get('segments', []))} edited segments, {len(original_data.get('segments', []))} original segments")
            return edited_data, original_data
            
        except Exception as e:
            logger.error(f"Error loading transcript data: {e}")
            raise
    
    def find_transcript_differences(self, original_data: dict, edited_data: dict) -> List[Dict]:
        """Find differences between original and edited transcripts"""
        differences = []
        
        original_segments = original_data.get("segments", [])
        edited_segments = edited_data.get("segments", [])
        
        # Create lookup by timing for comparison
        for i, (orig_seg, edit_seg) in enumerate(zip(original_segments, edited_segments)):
            # Check if text content differs
            orig_text = orig_seg.get("text", "").strip()
            edit_text = edit_seg.get("text", "").strip()
            
            if orig_text != edit_text:
                difference = {
                    "segment_index": i,
                    "start_time": orig_seg.get("start", 0),
                    "end_time": orig_seg.get("end", 0),
                    "original_text": orig_text,
                    "edited_text": edit_text,
                    "speaker": orig_seg.get("speaker", "SPEAKER_00"),
                    "words": edit_seg.get("words", [])                }
                differences.append(difference)
        
        logger.info(f"Found {len(differences)} transcript differences")
        return differences
    
    def generate_cloned_speech(self, text: str, speaker_id: str, output_path: str = None) -> str:
        """Generate speech using xTTS voice cloning for specific speaker"""
        if self.tts_model is None:
            raise RuntimeError("TTS model is not initialized. Cannot generate cloned speech.")
            
        if speaker_id not in self.speaker_voice_samples:
            raise ValueError(f"Voice sample for speaker {speaker_id} not found. Available speakers: {list(self.speaker_voice_samples.keys())}")
        
        try:
            speaker_sample_path = self.speaker_voice_samples[speaker_id]
            
            if not output_path:
                output_path = f"generated_{speaker_id}_{hash(text) % 100000}.wav"
            
            # Generate speech with xTTS voice cloning
            self.tts_model.tts_to_file(
                text=text,
                speaker_wav=speaker_sample_path,
                file_path=output_path,
                language="en"
            )
            
            logger.info(f"Generated cloned speech for {speaker_id}: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error generating cloned speech for {speaker_id}: {e}")
            raise
    
    def create_modified_audio_timeline(self, differences: List[Dict], output_dir: str = "tts_output") -> str:
        """Create complete audio timeline with cloned speech - simple overlay approach"""
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            # Load original audio
            original_audio = AudioSegment.from_file(self.original_audio_path)
            logger.info(f"Original audio duration: {len(original_audio)/1000:.2f}s")
            
            # Start with a copy of the original audio
            final_audio = original_audio
            
            # Sort differences by start time to process in order
            differences_sorted = sorted(differences, key=lambda x: x["start_time"])
            
            for i, diff in enumerate(differences_sorted):
                start_time = diff["start_time"]
                end_time = diff["end_time"]
                edited_text = diff["edited_text"]
                speaker_id = diff["speaker"]
                
                logger.info(f"Processing segment {i+1}/{len(differences_sorted)}: {start_time:.2f}s-{end_time:.2f}s, Speaker: {speaker_id}")
                logger.info(f"Original text: '{diff['original_text']}'")
                logger.info(f"Edited text: '{edited_text}'")
                
                # Generate cloned speech for edited text
                cloned_audio_path = self.generate_cloned_speech(
                    edited_text, 
                    speaker_id, 
                    os.path.join(output_dir, f"cloned_{diff['segment_index']}_{speaker_id}.wav")
                )
                
                # Load cloned audio
                cloned_audio = AudioSegment.from_file(cloned_audio_path)
                logger.info(f"Cloned audio duration: {len(cloned_audio)/1000:.2f}s")
                
                # Calculate positions in milliseconds
                start_ms = int(start_time * 1000)
                end_ms = int(end_time * 1000)
                original_segment_duration = end_ms - start_ms
                cloned_duration = len(cloned_audio)
                
                logger.info(f"Original segment: {original_segment_duration}ms, Cloned: {cloned_duration}ms")
                
                # Method 1: Simple replacement - replace the exact time segment
                # First, silence the original segment
                silence = AudioSegment.silent(duration=original_segment_duration)
                final_audio = final_audio[:start_ms] + silence + final_audio[end_ms:]
                
                # Then overlay the cloned audio at the same position
                # If cloned audio is longer, it will extend beyond the original segment
                # If shorter, it will be padded with the existing silence
                final_audio = final_audio.overlay(cloned_audio, position=start_ms)
                
                logger.info(f"Replaced segment {i+1}, final audio duration now: {len(final_audio)/1000:.2f}s")
            
            # Export final audio
            output_path = os.path.join(output_dir, "final_edited_audio.wav")
            final_audio.export(output_path, format="wav")
            
            logger.info(f"Final audio exported: {output_path}")
            logger.info(f"Final duration: {len(final_audio)/1000:.2f}s (Original: {len(original_audio)/1000:.2f}s)")
            
            return output_path
            
        except Exception as e:
            logger.error(f"Error creating modified audio timeline: {e}")
            raise
    
    def create_modified_audio_timeline_v2(self, differences: List[Dict], output_dir: str = "tts_output") -> str:
        """Alternative method: Build timeline from scratch to preserve all content"""
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            # Load original audio
            original_audio = AudioSegment.from_file(self.original_audio_path)
            logger.info(f"Original audio duration: {len(original_audio)/1000:.2f}s")
            
            # Sort differences by start time
            differences_sorted = sorted(differences, key=lambda x: x["start_time"])
            
            # Build timeline segments
            timeline_segments = []
            last_end_time = 0.0
            
            for i, diff in enumerate(differences_sorted):
                start_time = diff["start_time"]
                end_time = diff["end_time"]
                
                # Add original audio before this edit (if any gap)
                if start_time > last_end_time:
                    gap_start_ms = int(last_end_time * 1000)
                    gap_end_ms = int(start_time * 1000)
                    gap_audio = original_audio[gap_start_ms:gap_end_ms]
                    timeline_segments.append({
                        "audio": gap_audio,
                        "type": "original_gap",
                        "start": last_end_time,
                        "end": start_time,
                        "duration": len(gap_audio) / 1000.0
                    })
                    logger.info(f"Added original gap: {last_end_time:.2f}s-{start_time:.2f}s ({len(gap_audio)/1000:.2f}s)")
                
                # Generate and add cloned speech
                edited_text = diff["edited_text"]
                speaker_id = diff["speaker"]
                
                cloned_audio_path = self.generate_cloned_speech(
                    edited_text, 
                    speaker_id, 
                    os.path.join(output_dir, f"cloned_v2_{diff['segment_index']}_{speaker_id}.wav")
                )
                
                cloned_audio = AudioSegment.from_file(cloned_audio_path)
                timeline_segments.append({
                    "audio": cloned_audio,
                    "type": "cloned",
                    "start": start_time,
                    "end": end_time,
                    "duration": len(cloned_audio) / 1000.0,
                    "text": edited_text
                })
                logger.info(f"Added cloned segment: {start_time:.2f}s-{end_time:.2f}s ({len(cloned_audio)/1000:.2f}s) - '{edited_text}'")
                
                last_end_time = end_time
            
            # Add remaining original audio after last edit
            if last_end_time < len(original_audio) / 1000.0:
                remaining_start_ms = int(last_end_time * 1000)
                remaining_audio = original_audio[remaining_start_ms:]
                timeline_segments.append({
                    "audio": remaining_audio,
                    "type": "original_end",
                    "start": last_end_time,
                    "end": len(original_audio) / 1000.0,
                    "duration": len(remaining_audio) / 1000.0
                })
                logger.info(f"Added original ending: {last_end_time:.2f}s-{len(original_audio)/1000.0:.2f}s ({len(remaining_audio)/1000:.2f}s)")
            
            # Assemble final audio by concatenating all segments
            final_audio = AudioSegment.empty()
            total_expected_duration = 0.0
            
            for i, segment in enumerate(timeline_segments):
                final_audio += segment["audio"]
                total_expected_duration += segment["duration"]
                logger.info(f"Segment {i+1}: {segment['type']} - {segment['duration']:.2f}s (cumulative: {len(final_audio)/1000:.2f}s)")
            
            # Export final audio
            output_path = os.path.join(output_dir, "final_edited_audio_v2.wav")
            final_audio.export(output_path, format="wav")
            
            logger.info(f"Final audio exported: {output_path}")
            logger.info(f"Final duration: {len(final_audio)/1000:.2f}s")
            logger.info(f"Expected duration: {total_expected_duration:.2f}s")
            logger.info(f"Original duration: {len(original_audio)/1000:.2f}s")
            
            return output_path
            
        except Exception as e:
            logger.error(f"Error creating modified audio timeline v2: {e}")
            raise
    
    def process_full_transcript_editing(self, edited_transcript_path: str = None, 
                                      original_transcript_path: str = None,
                                      output_dir: str = "tts_output") -> str:
        """Complete workflow to process transcript edits and generate final audio"""
        try:
            # Load transcript data
            edited_data, original_data = self.load_transcript_data(edited_transcript_path, original_transcript_path)
            
            # Find differences
            differences = self.find_transcript_differences(original_data, edited_data)
            
            if not differences:
                logger.info("No differences found between transcripts")
                return self.original_audio_path
              # Create modified audio using both methods for comparison
            logger.info("Creating modified audio using overlay method...")
            final_audio_path_v1 = self.create_modified_audio_timeline(differences, output_dir)
            
            logger.info("Creating modified audio using segment-building method...")
            final_audio_path_v2 = self.create_modified_audio_timeline_v2(differences, output_dir)
            
            logger.info(f"Method 1 (overlay): {final_audio_path_v1}")
            logger.info(f"Method 2 (segment-building): {final_audio_path_v2}")
            logger.info(f"Transcript editing processing complete!")
            
            # Return the V2 method result as it preserves content better
            return final_audio_path_v2
            
        except Exception as e:
            logger.error(f"Error in full transcript editing process: {e}")
            raise


def run_voice_cloning_service():
    """Main function to run the voice cloning TTS service"""
    try:
        # Initialize service
        tts_service = VoiceCloningTTSService()
        
        # Process transcript editing and generate final audio
        final_audio_path = tts_service.process_full_transcript_editing()
        
        print(f"Voice cloning TTS processing completed!")
        print(f"Final audio with cloned voices: {final_audio_path}")
        
        return final_audio_path
        
    except Exception as e:
        logger.error(f"Voice cloning service failed: {e}")
        raise

if __name__ == "__main__":
    run_voice_cloning_service()
