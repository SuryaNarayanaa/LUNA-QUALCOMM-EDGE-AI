from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from concurrent.futures import ThreadPoolExecutor
import tempfile
import os
import shutil
from typing import Dict, Any

import google.generativeai as genai
from pydantic import BaseModel
from pydub import AudioSegment

from services.tts_service import run_voice_cloning_service
from services.transcribe import extract_audio_from_video, transcribe, diarize, assign_speakers, save_to_json, OUTPUT_DIR
from services.speaker_segmentation import SpeakerSegmentationService
from fastapi.middleware.cors import CORSMiddleware

try:
    import fal_client
except ImportError:  # fal-client is optional; only needed for lip sync
    fal_client = None
MEDIA_DIR = os.path.join(os.getcwd(), "assests", "users_segements")
VIDEO_CACHE_PATH = os.path.join(os.getcwd(), "assests", "video", "uploaded_video.mp4")
os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(os.path.dirname(VIDEO_CACHE_PATH), exist_ok=True)
LAST_VIDEO_PATH = None

# Apply CORS
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust as needed for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")


def process_video_analysis(video_path: str) -> Dict[str, Any]:
    try:
        audio_path = "assests/audio/extracted_audio.wav"
        os.makedirs(os.path.dirname(audio_path), exist_ok=True)
        extract_audio_from_video(video_path, audio_path)

        with ThreadPoolExecutor(max_workers=2) as executor:
            transcribe_future = executor.submit(transcribe, audio_path)
            diarize_future = executor.submit(diarize, audio_path)

            transcript = transcribe_future.result()
            diarize_df, audio = diarize_future.result()

        transcript = assign_speakers(diarize_df, transcript, fill_nearest=False)

        transcript_file_path = os.path.join(OUTPUT_DIR, "transcript.json")
        save_to_json(transcript, transcript_file_path)

        segmenter = SpeakerSegmentationService()

        audio_paths = segmenter.process_speaker_segmentation(transcript_file_path)

        statistics = generate_statistics(transcript.get("segments", []), diarize_df)
    
        
        return {
            "transcription": transcript,
            "statistics": statistics,
            "status": "success"
        }
    
    except Exception as e:
        return {
            "error": str(e),
            "status": "failed"
        }

def generate_statistics(combined_data, diarize_df) -> Dict[str, Any]:
    """Generate statistics from the analysis results."""
    try:
        speakers = set()
        total_words = 0
        speaker_word_counts = {}
        
        for segment in combined_data:
            if not isinstance(segment, dict):
                print(f"Warning: Skipping non-dictionary segment: {segment}")
                continue

            speaker = segment.get('speaker', 'Unknown')
            speakers.add(speaker)
            words = len(segment.get('text', '').split())
            total_words += words
            speaker_word_counts[speaker] = speaker_word_counts.get(speaker, 0) + words
        
        # Calculate speaking time per speaker from the diarization data.
        speaker_times = {}
        for speaker in speakers:
            speaker_segments = diarize_df[diarize_df['speaker'] == speaker]
            total_time = (speaker_segments['end'] - speaker_segments['start']).sum()
            speaker_times[speaker] = float(total_time)
        
        return {
            "total_speakers": len(speakers),
            "total_words": total_words,
            "speaker_word_counts": speaker_word_counts,
            "speaker_speaking_times": speaker_times,
            "speakers_list": list(speakers)
        }
    
    except Exception as e:
        return {"error": f"Statistics generation failed: {str(e)}"}

@app.post("/analyze-video/")
async def analyze_video(file: UploadFile = File(...)):
    try:
        # Validate file type
        if not file.filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
            raise HTTPException(status_code=400, detail="Invalid file format. Please upload a video file.")
        
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_video_path = temp_file.name

        # Keep a copy of the uploaded video for lip sync/output reuse
        try:
            shutil.copyfile(temp_video_path, VIDEO_CACHE_PATH)
            global LAST_VIDEO_PATH
            LAST_VIDEO_PATH = VIDEO_CACHE_PATH
        except Exception:
            # Non-fatal; log in real setup
            pass
        
        try:
            # Process the video
            result = process_video_analysis(temp_video_path)
            
            return JSONResponse(content=result)
        
        finally:
            # Clean up temporary video file
            if os.path.exists(temp_video_path):
                os.remove(temp_video_path)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
class TranscriptEdit(BaseModel):
    segments: Any
    lip_sync: bool = False

@app.post("/edit-transcript/")
async def edit_transcript(request: Request, transcript: TranscriptEdit):
    try:
        output_path = os.path.join(OUTPUT_DIR, "transcript-edited.json")
        save_to_json({"segments": transcript.segments}, output_path)

        final_audio_path = run_voice_cloning_service()

        # Copy audio into served media directory
        audio_filename = os.path.basename(final_audio_path)
        served_audio_path = os.path.join(MEDIA_DIR, audio_filename)
        shutil.copyfile(final_audio_path, served_audio_path)

        # Duration metadata for sync
        audio_duration = AudioSegment.from_file(served_audio_path).duration_seconds

        base_url = str(request.base_url).rstrip("/")
        audio_url = f"{base_url}/media/{audio_filename}"

        lipsync_video_url = None
        if transcript.lip_sync and LAST_VIDEO_PATH and fal_client and os.getenv("FAL_KEY"):
            try:
                lipsync_video_url = run_lipsync(LAST_VIDEO_PATH, served_audio_path)
            except Exception:
                lipsync_video_url = None

        return {
            "audio_url": audio_url,
            "audio_duration_sec": audio_duration,
            "lipsync_video_url": lipsync_video_url,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save transcript: {str(e)}")
@app.post("/analyze-video-path/")
async def analyze_video_from_path(video_path: str):
    try:
        if not os.path.exists(video_path):
            raise HTTPException(status_code=404, detail="Video file not found")

        try:
            shutil.copyfile(video_path, VIDEO_CACHE_PATH)
            global LAST_VIDEO_PATH
            LAST_VIDEO_PATH = VIDEO_CACHE_PATH
        except Exception:
            pass
        
        result = process_video_analysis(video_path)
        
        return JSONResponse(content=result)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
class SummarizeRequest(BaseModel):
    context: str
    language: str = "English"


_gemini_model = None


def _get_gemini_model():
    """Lazy-init the Gemini model so we only configure once."""
    global _gemini_model
    if _gemini_model is None:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("Set GEMINI_API_KEY (or GOOGLE_GEMINI_API_KEY) in the environment.")

        genai.configure(api_key=api_key)
        model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        _gemini_model = genai.GenerativeModel(model_name)
    return _gemini_model


def summarize_text(context: str, language: str = "English") -> str:
    prompt = (
        "You are a concise summarizer. "
        f"Summarize the following text in {language} with clear bullet points and a 1-2 line overview.\n\n"
        f"Text:\n{context}"
    )
    model = _get_gemini_model()
    response = model.generate_content(prompt)
    return response.text

@app.post("/summarize")
def summarize_endpoint(request: SummarizeRequest):
    summary = summarize_text(request.context, request.language)
    return {"summary": summary}


def run_lipsync(video_path: str, audio_path: str) -> str:
    if not fal_client:
        raise RuntimeError("fal-client is not installed; cannot run lip sync.")
    if not os.getenv("FAL_KEY"):
        raise RuntimeError("FAL_KEY not set in environment; cannot run lip sync.")

    video_url = fal_client.upload_file(video_path)
    audio_url = fal_client.upload_file(audio_path)

    result = fal_client.subscribe(
        "veed/lipsync",
        arguments={
            "video_url": video_url,
            "audio_url": audio_url,
        },
        with_logs=False,
    )

    video_result = result.get("video")
    if not video_result or not video_result.get("url"):
        raise RuntimeError("Lip sync did not return a video URL.")

    return video_result["url"]
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000 )