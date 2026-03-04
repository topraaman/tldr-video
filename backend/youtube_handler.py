"""YouTube and podcast audio extraction using yt-dlp"""
import os
import sys
import subprocess
import re
import json
import httpx
from pathlib import Path
from urllib.parse import urlparse

# Allowed hostnames for thumbnail downloads (SSRF prevention)
_ALLOWED_THUMBNAIL_HOSTS = {
    "i.ytimg.com",
    "i9.ytimg.com",
    "img.youtube.com",
    "yt3.ggpht.com",
    "yt3.googleusercontent.com",
    "i.imgur.com",
    "cdn.podbean.com",
    "images.transistor.fm",
    "d3t3ozftmdmh3i.cloudfront.net",
    "megaphone.imgix.net",
    "anchor.fm",
    "podcasts.apple.com",
    "is1-ssl.mzstatic.com",
}

DOWNLOADS_DIR = Path(__file__).parent.parent / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

# Use yt-dlp from the same Python environment
YTDLP_PATH = os.path.join(os.path.dirname(sys.executable), "yt-dlp")


def sanitize_filename(title: str) -> str:
    """Remove invalid characters from filename"""
    return re.sub(r'[<>:"/\\|?*]', '', title)[:100]


def download_thumbnail(thumbnail_url: str, video_id: str) -> str:
    """Download thumbnail image and return local path"""
    if not thumbnail_url:
        return None

    # SSRF prevention: only fetch from known-safe image CDN hostnames
    try:
        parsed = urlparse(thumbnail_url)
        host = parsed.hostname or ""
        if parsed.scheme not in ("http", "https"):
            return None
        if not any(host == allowed or host.endswith("." + allowed)
                   for allowed in _ALLOWED_THUMBNAIL_HOSTS):
            return None
    except Exception:
        return None

    thumbnail_path = str(DOWNLOADS_DIR / f"{video_id}_thumb.jpg")

    try:
        response = httpx.get(thumbnail_url, timeout=30, follow_redirects=False)
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
        YTDLP_PATH,
        "--dump-json",
        "--no-download",
        "--no-playlist",
        "--extractor-args", "youtube:player_client=android,mweb",
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
        YTDLP_PATH,
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--output", output_template,
        "--no-playlist",
        "--quiet",
        "--progress",
        "--extractor-args", "youtube:player_client=android,mweb",
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


def extract_video(url: str, max_height: int = 1080) -> dict:
    """
    Extract video from YouTube URL for reel generation.
    Downloads video with audio, limited to specified max height.

    Returns dict with video_path, title, duration, and thumbnail_path.
    """
    # Step 1: Get video info first (fast, no download)
    info_cmd = [
        YTDLP_PATH,
        "--dump-json",
        "--no-download",
        "--no-playlist",
        "--extractor-args", "youtube:player_client=android,mweb",
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

    # Step 2: Download video with audio
    output_template = str(DOWNLOADS_DIR / f"{video_id}_video.%(ext)s")

    # Format selection: best video up to max_height with best audio, merged to mp4
    format_spec = f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]"

    download_cmd = [
        YTDLP_PATH,
        "-f", format_spec,
        "--merge-output-format", "mp4",
        "--output", output_template,
        "--no-playlist",
        "--quiet",
        "--progress",
        "--extractor-args", "youtube:player_client=android,mweb",
        url
    ]

    download_result = subprocess.run(download_cmd, capture_output=True, text=True, timeout=600)

    if download_result.returncode != 0:
        raise Exception(f"yt-dlp video download error: {download_result.stderr}")

    # Find the downloaded file
    video_path = str(DOWNLOADS_DIR / f"{video_id}_video.mp4")

    if not os.path.exists(video_path):
        # Try to find any video file with this video_id
        for f in DOWNLOADS_DIR.glob(f"{video_id}_video*"):
            video_path = str(f)
            break

    if not os.path.exists(video_path):
        raise Exception(f"Downloaded video file not found: {video_path}")

    return {
        "video_path": video_path,
        "title": title,
        "duration": float(duration) if duration else 0,
        "thumbnail_path": thumbnail_path,
        "channel": channel,
        "video_id": video_id
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


def cleanup_video(video_path: str):
    """Remove downloaded video file"""
    try:
        if video_path and os.path.exists(video_path):
            os.remove(video_path)
    except Exception:
        pass


if __name__ == "__main__":
    # Test with a short video
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    print(f"Testing with: {test_url}")
    result = extract_audio(test_url)
    print(f"Result: {result}")
