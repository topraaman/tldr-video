"""FastAPI server for Video-to-Transcript application"""
import os
import asyncio
import logging
import time
from collections import defaultdict
from pathlib import Path
from fastapi import Request

logger = logging.getLogger(__name__)

# Simple in-memory rate limiter: max 5 heavy requests per IP per 60 seconds
_rate_limit_store: dict = defaultdict(list)
_RATE_LIMIT_MAX = 5
_RATE_LIMIT_WINDOW = 60  # seconds


def _check_rate_limit(ip: str) -> bool:
    """Return True if the request is allowed, False if rate-limited."""
    now = time.monotonic()
    window_start = now - _RATE_LIMIT_WINDOW
    timestamps = _rate_limit_store[ip]
    # Drop expired entries
    _rate_limit_store[ip] = [t for t in timestamps if t > window_start]
    if len(_rate_limit_store[ip]) >= _RATE_LIMIT_MAX:
        return False
    _rate_limit_store[ip].append(now)
    return True
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from typing import Optional

from youtube_handler import extract_audio, cleanup_audio, extract_video, cleanup_video
from transcriber import transcribe_audio, segments_to_text_with_timestamps
from llm_processor import (
    generate_chapters_and_takeaways,
    format_transcript_with_sections,
    translate_text,
    check_ollama_running,
    identify_reel_segments,
    segments_to_chapter_suggestions
)
from exporters import export_to_pdf, export_to_docx
from video_clipper import create_reel, cleanup_reel, cleanup_old_reels, REELS_DIR

app = FastAPI(title="Video to Transcript", version="1.0.0")

# CORS for frontend — localhost only
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Serve frontend
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# Store active jobs
jobs = {}


class TranscriptRequest(BaseModel):
    url: str
    language: str = "auto"  # 'auto', 'en', 'ta', 'hi', etc.


class TranslateRequest(BaseModel):
    text: str
    source_lang: str = "en"
    target_lang: str = "ta"


class ExportRequest(BaseModel):
    title: str
    chapters: list
    takeaways: list
    transcript: str
    format: str = "pdf"  # "pdf" or "docx"
    font_name: str = "Arial"
    font_size: int = 11
    highlights: Optional[list] = None
    # Accept only a basename; server resolves the full path within DOWNLOADS_DIR
    thumbnail_filename: Optional[str] = None
    channel: Optional[str] = ""


class JobStatus(BaseModel):
    job_id: str
    status: str  # "downloading", "transcribing", "processing", "complete", "error"
    progress: int  # 0-100
    message: str
    result: Optional[dict] = None


class ReelSuggestRequest(BaseModel):
    """Request AI-suggested reel segments"""
    transcript: str
    segments: list
    title: str = ""
    chapters: Optional[list] = None


class ReelGenerateRequest(BaseModel):
    """Request to generate a reel clip"""
    url: str  # Video URL for downloading
    start_time: float  # Start time in seconds
    end_time: float  # End time in seconds
    title: str = "reel"  # Title for the output file
    segments: Optional[list] = None  # Transcript segments for captions
    include_captions: bool = True
    blur_background: bool = True


# Store reel generation jobs
reel_jobs = {}


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


DOWNLOADS_DIR = Path(__file__).parent.parent / "downloads"


@app.get("/api/thumbnail/{filename}")
async def get_thumbnail(filename: str):
    """Serve thumbnail image for download"""
    # Reject any path separators before resolving
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not filename.endswith(('_thumb.jpg', '_thumb.png')):
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    # Resolve and assert the final path stays inside DOWNLOADS_DIR
    thumbnail_path = (DOWNLOADS_DIR / filename).resolve()
    if not str(thumbnail_path).startswith(str(DOWNLOADS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not thumbnail_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    return FileResponse(
        thumbnail_path,
        media_type="image/jpeg",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.post("/api/transcribe")
async def transcribe_video(request: TranscriptRequest, background_tasks: BackgroundTasks, req: Request):
    """
    Start transcription job for a video/podcast URL.
    Returns job_id to poll for status.
    """
    client_ip = req.client.host if req.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait before submitting again.")

    import uuid
    job_id = str(uuid.uuid4())

    jobs[job_id] = {
        "status": "starting",
        "progress": 0,
        "message": "Starting...",
        "result": None
    }

    # Run transcription in background
    background_tasks.add_task(process_transcription, job_id, request.url, request.language)

    return {"job_id": job_id}


async def process_transcription(job_id: str, url: str, language: str = "auto"):
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
        lang_display = language if language != "auto" else "auto-detecting"
        jobs[job_id] = {
            "status": "transcribing",
            "progress": 30,
            "message": f"Transcribing audio ({lang_display})...",
            "result": None
        }

        # Pass language to transcriber
        from functools import partial
        transcribe_fn = partial(transcribe_audio, audio_path, language)
        transcript_result = await loop.run_in_executor(None, transcribe_fn)

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

        # Complete — return only the filename (not full path) to avoid path leakage
        thumbnail_filename = Path(thumbnail_path).name if thumbnail_path else None

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
                "thumbnail_filename": thumbnail_filename,
                "channel": channel
            }
        }

    except Exception as e:
        logger.error("Transcription job %s failed: %s", job_id, e, exc_info=True)
        jobs[job_id] = {
            "status": "error",
            "progress": 0,
            "message": "Transcription failed. Check server logs for details.",
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
        # Resolve thumbnail path safely — only allow filenames within DOWNLOADS_DIR
        thumbnail_path = None
        if request.thumbnail_filename:
            fname = request.thumbnail_filename
            if "/" not in fname and "\\" not in fname and ".." not in fname:
                candidate = (DOWNLOADS_DIR / fname).resolve()
                if str(candidate).startswith(str(DOWNLOADS_DIR.resolve())) and candidate.exists():
                    thumbnail_path = str(candidate)

        if request.format == "pdf":
            content = export_to_pdf(
                title=request.title,
                chapters=request.chapters,
                takeaways=request.takeaways,
                transcript=request.transcript,
                font_name=request.font_name,
                font_size=request.font_size,
                highlights=request.highlights,
                thumbnail_path=thumbnail_path,
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
                thumbnail_path=thumbnail_path,
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
        logger.error("Export failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Export failed. Check server logs for details.")


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
        logger.error("Chapter regeneration failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Chapter regeneration failed. Check server logs for details.")


# ============ REELS API ENDPOINTS ============

@app.post("/api/reels/suggest")
async def suggest_reels(request: ReelSuggestRequest):
    """
    Get AI-suggested segments for Instagram Reels.
    Also includes chapter-based suggestions if chapters are provided.
    """
    try:
        # Get AI suggestions
        ai_result = await identify_reel_segments(
            transcript=request.transcript,
            segments=request.segments,
            title=request.title
        )

        ai_suggestions = ai_result.get("reel_segments", [])

        # Get chapter-based suggestions if chapters provided
        chapter_suggestions = []
        if request.chapters:
            chapter_suggestions = segments_to_chapter_suggestions(
                chapters=request.chapters,
                segments=request.segments
            )

        return {
            "ai_suggestions": ai_suggestions,
            "chapter_suggestions": chapter_suggestions
        }

    except Exception as e:
        logger.error("Reel suggestion failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Reel suggestion failed. Check server logs for details.")


@app.post("/api/reels/generate")
async def generate_reel(request: ReelGenerateRequest, background_tasks: BackgroundTasks, req: Request):
    """
    Start reel generation job.
    Downloads video, extracts clip, converts to vertical, adds captions.
    Returns job_id to poll for status.
    """
    import uuid

    client_ip = req.client.host if req.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait before submitting again.")

    # Validate duration
    duration = request.end_time - request.start_time
    if duration < 5:
        raise HTTPException(status_code=400, detail="Reel must be at least 5 seconds")
    if duration > 60:
        raise HTTPException(status_code=400, detail="Reel cannot exceed 60 seconds")

    job_id = str(uuid.uuid4())

    reel_jobs[job_id] = {
        "status": "starting",
        "progress": 0,
        "message": "Starting reel generation...",
        "result": None
    }

    # Run reel generation in background
    background_tasks.add_task(
        process_reel_generation,
        job_id,
        request.url,
        request.start_time,
        request.end_time,
        request.title,
        request.segments,
        request.include_captions,
        request.blur_background
    )

    return {"job_id": job_id}


async def process_reel_generation(
    job_id: str,
    url: str,
    start_time: float,
    end_time: float,
    title: str,
    segments: list,
    include_captions: bool,
    blur_background: bool
):
    """Background task to generate a reel"""
    video_path = None

    try:
        # Cleanup old reels first
        cleanup_old_reels(max_age_hours=1)

        # Step 1: Download video
        reel_jobs[job_id] = {
            "status": "downloading",
            "progress": 10,
            "message": "Downloading video...",
            "result": None
        }

        loop = asyncio.get_event_loop()
        video_info = await loop.run_in_executor(None, extract_video, url)
        video_path = video_info["video_path"]
        video_id = video_info.get("video_id", "video")

        # Step 2: Create reel
        reel_jobs[job_id] = {
            "status": "processing",
            "progress": 50,
            "message": "Creating vertical clip with captions...",
            "result": None
        }

        # Sanitize title for filename - only allow alphanumeric, underscore, hyphen
        import re
        safe_title = re.sub(r'[^a-zA-Z0-9_\-]', '_', title)[:50]
        safe_title = re.sub(r'_+', '_', safe_title).strip('_')  # Remove multiple underscores
        output_filename = f"{video_id}_{safe_title}_{int(start_time)}_{int(end_time)}"

        from functools import partial
        create_reel_fn = partial(
            create_reel,
            video_path=video_path,
            start_time=start_time,
            end_time=end_time,
            output_filename=output_filename,
            segments=segments,
            include_captions=include_captions,
            blur_background=blur_background
        )

        reel_result = await loop.run_in_executor(None, create_reel_fn)

        # Complete
        reel_jobs[job_id] = {
            "status": "complete",
            "progress": 100,
            "message": "Reel ready!",
            "result": {
                "reel_id": output_filename,
                "reel_path": reel_result["reel_path"],
                "duration": reel_result["duration"],
                "dimensions": reel_result["dimensions"],
                "has_captions": reel_result["has_captions"]
            }
        }

    except Exception as e:
        logger.error("Reel job %s failed: %s", job_id, e, exc_info=True)
        reel_jobs[job_id] = {
            "status": "error",
            "progress": 0,
            "message": "Reel generation failed. Check server logs for details.",
            "result": None
        }

    finally:
        # Cleanup video file
        if video_path:
            cleanup_video(video_path)


@app.get("/api/reels/job/{job_id}")
async def get_reel_job_status(job_id: str):
    """Get status of a reel generation job"""
    if job_id not in reel_jobs:
        raise HTTPException(status_code=404, detail="Reel job not found")
    return reel_jobs[job_id]


@app.get("/api/reels/download/{reel_id}")
async def download_reel(reel_id: str):
    """Download a generated reel"""
    # Security: validate reel_id format
    import re
    if not re.match(r'^[\w\-]+$', reel_id):
        raise HTTPException(status_code=400, detail="Invalid reel ID")

    reel_path = REELS_DIR / f"{reel_id}.mp4"

    if not reel_path.exists():
        raise HTTPException(status_code=404, detail="Reel not found")

    return FileResponse(
        reel_path,
        media_type="video/mp4",
        filename=f"{reel_id}.mp4",
        headers={"Content-Disposition": f'attachment; filename="{reel_id}.mp4"'}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
