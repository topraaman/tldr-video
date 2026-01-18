"""YouTube and podcast audio extraction using yt-dlp"""
import os
import subprocess
import re
import json
import httpx
from pathlib import Path

DOWNLOADS_DIR = Path(__file__).parent.parent / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)


def sanitize_filename(title: str) -> str:
    """Remove invalid characters from filename"""
    return re.sub(r'[<>:"/\\|?*]', '', title)[:100]


def download_thumbnail(thumbnail_url: str, video_id: str) -> str:
    """Download thumbnail image and return local path"""
    if not thumbnail_url:
        return None

    thumbnail_path = str(DOWNLOADS_DIR / f"{video_id}_thumb.jpg")

    try:
        response = httpx.get(thumbnail_url, timeout=30, follow_redirects=True)
        if response.status_code == 200:
            with open(thumbnail_path, 'wb') as f:
                f.write(response.content)
            return thumbnail_path
    except Exception:
        pass

    return None


def extract_audio(url: str) -> dict:
    """
    Extract audio from YouTube video or podcast URL.
    Returns dict with audio_path, title, duration, and thumbnail_path.
    """
    # Step 1: Get video info first (fast, no download)
    info_cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-download",
        "--no-playlist",
        url
    ]

    info_result = subprocess.run(info_cmd, capture_output=True, text=True, timeout=60)

    title = "Unknown"
    duration = 0
    video_id = "video"
    thumbnail_url = None
    channel = ""

    if info_result.returncode == 0:
        try:
            info = json.loads(info_result.stdout)
            title = info.get("title", "Unknown")
            duration = info.get("duration", 0)
            video_id = info.get("id", "video")
            thumbnail_url = info.get("thumbnail", "")
            channel = info.get("channel", info.get("uploader", ""))
        except json.JSONDecodeError:
            pass

    # Download thumbnail
    thumbnail_path = download_thumbnail(thumbnail_url, video_id)

    # Step 2: Download audio
    output_template = str(DOWNLOADS_DIR / f"{video_id}.%(ext)s")

    download_cmd = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--output", output_template,
        "--no-playlist",
        "--quiet",
        "--progress",
        url
    ]

    download_result = subprocess.run(download_cmd, capture_output=True, text=True, timeout=300)

    if download_result.returncode != 0:
        raise Exception(f"yt-dlp download error: {download_result.stderr}")

    # Find the downloaded file
    audio_path = str(DOWNLOADS_DIR / f"{video_id}.mp3")

    if not os.path.exists(audio_path):
        # Try to find any mp3 file with this video_id
        for f in DOWNLOADS_DIR.glob(f"{video_id}*"):
            audio_path = str(f)
            break

    if not os.path.exists(audio_path):
        raise Exception(f"Downloaded file not found: {audio_path}")

    return {
        "audio_path": audio_path,
        "title": title,
        "duration": float(duration) if duration else 0,
        "thumbnail_path": thumbnail_path,
        "channel": channel
    }


def cleanup_audio(audio_path: str, thumbnail_path: str = None):
    """Remove downloaded audio and thumbnail files"""
    try:
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
        if thumbnail_path and os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
    except Exception:
        pass


if __name__ == "__main__":
    # Test with a short video
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    print(f"Testing with: {test_url}")
    result = extract_audio(test_url)
    print(f"Result: {result}")
