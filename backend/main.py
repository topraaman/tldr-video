"""FastAPI server for Video-to-Transcript application"""
import os
import asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from typing import Optional

from youtube_handler import extract_audio, cleanup_audio
from transcriber import transcribe_audio, segments_to_text_with_timestamps
from llm_processor import generate_chapters_and_takeaways, format_transcript_with_sections, check_ollama_running
from exporters import export_to_pdf, export_to_docx

app = FastAPI(title="Video to Transcript", version="1.0.0")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# Store active jobs
jobs = {}


class TranscriptRequest(BaseModel):
    url: str


class ExportRequest(BaseModel):
    title: str
    chapters: list
    takeaways: list
    transcript: str
    format: str = "pdf"  # "pdf" or "docx"
    font_name: str = "Arial"
    font_size: int = 11
    highlights: Optional[list] = None
    thumbnail_path: Optional[str] = None
    channel: Optional[str] = ""


class JobStatus(BaseModel):
    job_id: str
    status: str  # "downloading", "transcribing", "processing", "complete", "error"
    progress: int  # 0-100
    message: str
    result: Optional[dict] = None


@app.get("/")
async def root():
    """Serve the main frontend page"""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
async def health_check():
    """Check if all services are running"""
    ollama_ok = check_ollama_running()
    return {
        "status": "ok" if ollama_ok else "degraded",
        "ollama": ollama_ok,
        "message": "Ready" if ollama_ok else "Ollama not running - start with 'ollama serve'"
    }


@app.get("/api/thumbnail/{filename}")
async def get_thumbnail(filename: str):
    """Serve thumbnail image for download"""
    # Security: only allow files from downloads directory
    thumbnail_path = Path(__file__).parent.parent / "downloads" / filename

    if not thumbnail_path.exists() or not filename.endswith(('_thumb.jpg', '_thumb.png')):
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    return FileResponse(
        thumbnail_path,
        media_type="image/jpeg",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.post("/api/transcribe")
async def transcribe_video(request: TranscriptRequest, background_tasks: BackgroundTasks):
    """
    Start transcription job for a video/podcast URL.
    Returns job_id to poll for status.
    """
    import uuid
    job_id = str(uuid.uuid4())[:8]

    jobs[job_id] = {
        "status": "starting",
        "progress": 0,
        "message": "Starting...",
        "result": None
    }

    # Run transcription in background
    background_tasks.add_task(process_transcription, job_id, request.url)

    return {"job_id": job_id}


async def process_transcription(job_id: str, url: str):
    """Background task to process transcription"""
    audio_path = None
    thumbnail_path = None

    try:
        # Step 1: Download audio
        jobs[job_id] = {
            "status": "downloading",
            "progress": 10,
            "message": "Downloading audio...",
            "result": None
        }

        loop = asyncio.get_event_loop()
        audio_info = await loop.run_in_executor(None, extract_audio, url)
        audio_path = audio_info["audio_path"]
        title = audio_info["title"]
        thumbnail_path = audio_info.get("thumbnail_path")
        channel = audio_info.get("channel", "")

        # Step 2: Transcribe
        jobs[job_id] = {
            "status": "transcribing",
            "progress": 30,
            "message": "Transcribing audio (this may take a few minutes)...",
            "result": None
        }

        transcript_result = await loop.run_in_executor(
            None, transcribe_audio, audio_path
        )

        # Step 3: Generate chapters and takeaways
        jobs[job_id] = {
            "status": "processing",
            "progress": 70,
            "message": "Generating chapters and takeaways...",
            "result": None
        }

        llm_result = await generate_chapters_and_takeaways(
            transcript_result["text"],
            transcript_result["segments"],
            title
        )

        # Step 4: Format transcript with sections and remove promo content
        jobs[job_id] = {
            "status": "processing",
            "progress": 85,
            "message": "Formatting transcript and removing promotional content...",
            "result": None
        }

        formatted_transcript = await format_transcript_with_sections(
            transcript_result["text"],
            llm_result.get("chapters", [])
        )

        # Complete
        jobs[job_id] = {
            "status": "complete",
            "progress": 100,
            "message": "Done!",
            "result": {
                "title": title,
                "transcript": formatted_transcript,  # Formatted with sections
                "raw_transcript": transcript_result["text"],  # Keep raw version too
                "segments": transcript_result["segments"],
                "chapters": llm_result.get("chapters", []),
                "takeaways": llm_result.get("takeaways", []),
                "language": transcript_result.get("language", "en"),
                "thumbnail_path": thumbnail_path,
                "channel": channel
            }
        }

    except Exception as e:
        jobs[job_id] = {
            "status": "error",
            "progress": 0,
            "message": str(e),
            "result": None
        }

    finally:
        # Cleanup audio file
        if audio_path:
            cleanup_audio(audio_path)


@app.get("/api/job/{job_id}")
async def get_job_status(job_id: str):
    """Get status of a transcription job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]


@app.post("/api/export")
async def export_document(request: ExportRequest):
    """Export transcript to PDF or DOCX with thumbnail"""
    try:
        if request.format == "pdf":
            content = export_to_pdf(
                title=request.title,
                chapters=request.chapters,
                takeaways=request.takeaways,
                transcript=request.transcript,
                font_name=request.font_name,
                font_size=request.font_size,
                highlights=request.highlights,
                thumbnail_path=request.thumbnail_path,
                channel=request.channel
            )
            media_type = "application/pdf"
            filename = f"{request.title[:50]}.pdf"
        else:
            content = export_to_docx(
                title=request.title,
                chapters=request.chapters,
                takeaways=request.takeaways,
                transcript=request.transcript,
                font_name=request.font_name,
                font_size=request.font_size,
                thumbnail_path=request.thumbnail_path,
                channel=request.channel
            )
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            filename = f"{request.title[:50]}.docx"

        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/regenerate-chapters")
async def regenerate_chapters(request: dict):
    """Regenerate chapters and takeaways for existing transcript"""
    try:
        segments = request.get("segments", [])
        transcript = request.get("transcript", "")
        title = request.get("title", "")

        result = await generate_chapters_and_takeaways(transcript, segments, title)
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
