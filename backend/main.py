from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from concurrent.futures import ThreadPoolExecutor
import tempfile
import os
from services.tts_service import run_voice_cloning_service
from imagine import ImagineClient, ChatMessage
from pydantic import BaseModel


from pprint import pprint
from typing import Dict, Any, List
from services.transcribe import extract_audio_from_video,transcribe,diarize,assign_speakers,save_to_json,OUTPUT_DIR
from services.speaker_segmentation import SpeakerSegmentationService
from fastapi.middleware.cors import CORSMiddleware
# Apply CORS
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust as needed for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app = FastAPI()

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

@app.post("/edit-transcript/")
async def edit_transcript(transcript: TranscriptEdit):
    try:
        output_path = os.path.join(OUTPUT_DIR, "transcript-edited.json")
        save_to_json({"segments": transcript.segments}, output_path)
        final_audio_path = run_voice_cloning_service()
        # Serve the audio file directly
        return FileResponse(final_audio_path, media_type="audio/wav", filename="final_edited_audio.wav")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save transcript: {str(e)}")
@app.post("/analyze-video-path/")
async def analyze_video_from_path(video_path: str):
    try:
        if not os.path.exists(video_path):
            raise HTTPException(status_code=404, detail="Video file not found")
        
        result = process_video_analysis(video_path)
        
        return JSONResponse(content=result)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
class SummarizeRequest(BaseModel):
    context: str

# init client
print("Setting up client...")
client = ImagineClient(
    api_key="f66499e9-2d54-4adf-85c1-5c9d67a13b1b",
    endpoint="http://10.190.147.82:5050/v2"
)
print("Client connected.")

# health check
print("Checking health...")
health = client.health_check()
pprint(health)

# list models
print("Listing models...")
models = client.get_available_models_by_type()
pprint(models)

def summarize_text(context: str, language: str = "English") -> str:
    """
    Summarizes the given context in the specified language using the Sarvam-m model.
    """
    prompt = f"Summarize the following text in {language}:\n{context}"
    response = client.chat(
        messages=[
            ChatMessage(role="user", content=prompt),
        ],
        model="Sarvam-m"
    )
    return response.first_content

class SummarizeRequest(BaseModel):
    context: str
    language: str = "English"

@app.post("/summarize")
def summarize_endpoint(request: SummarizeRequest):
    summary = summarize_text(request.context, request.language)
    return {"summary": summary}
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000 )