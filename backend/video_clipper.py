"""Video clipper for Instagram Reels generation using ffmpeg"""
import os
import subprocess
import tempfile
import json
from pathlib import Path
from typing import Optional
import shutil

DOWNLOADS_DIR = Path(__file__).parent.parent / "downloads"
REELS_DIR = DOWNLOADS_DIR / "reels"
REELS_DIR.mkdir(exist_ok=True)

# Instagram Reels dimensions (9:16 vertical)
REEL_WIDTH = 1080
REEL_HEIGHT = 1920


def get_video_info(video_path: str) -> dict:
    """Get video metadata using ffprobe"""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        video_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        raise Exception(f"ffprobe error: {result.stderr}")

    info = json.loads(result.stdout)

    # Find video stream
    video_stream = None
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    if not video_stream:
        raise Exception("No video stream found")

    return {
        "width": int(video_stream.get("width", 1920)),
        "height": int(video_stream.get("height", 1080)),
        "duration": float(info.get("format", {}).get("duration", 0)),
        "fps": (lambda r: int(r[0]) / int(r[1]) if len(r) == 2 and r[1] != '0' else 30.0)(
            video_stream.get("r_frame_rate", "30/1").split("/")
        )
    }


def extract_clip(
    video_path: str,
    start_time: float,
    end_time: float,
    output_path: str
) -> str:
    """
    Extract a clip from video between start and end timestamps.

    Args:
        video_path: Path to source video
        start_time: Start time in seconds
        end_time: End time in seconds
        output_path: Output file path

    Returns:
        Path to extracted clip
    """
    duration = end_time - start_time

    if duration <= 0:
        raise ValueError("End time must be greater than start time")

    if duration > 60:
        raise ValueError("Clip duration cannot exceed 60 seconds")

    cmd = [
        "ffmpeg",
        "-y",  # Overwrite output
        "-ss", str(start_time),  # Seek before input (faster)
        "-i", video_path,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        raise Exception(f"ffmpeg extract error: {result.stderr}")

    return output_path


def convert_to_vertical(
    video_path: str,
    output_path: str,
    blur_background: bool = True
) -> str:
    """
    Convert video to 9:16 vertical format for Instagram Reels.

    Uses blur background technique: blurred scaled video as background,
    original video centered on top.

    Args:
        video_path: Path to source video
        output_path: Output file path
        blur_background: If True, add blurred background; if False, use black bars

    Returns:
        Path to converted video
    """
    if blur_background:
        # Complex filter: blurred background with centered video overlay
        filter_complex = (
            # Create blurred background
            f"[0:v]scale={REEL_WIDTH}:{REEL_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={REEL_WIDTH}:{REEL_HEIGHT},boxblur=25:5[bg];"
            # Scale original to fit height while maintaining aspect ratio
            f"[0:v]scale=-1:{REEL_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"scale=trunc(iw/2)*2:trunc(ih/2)*2[fg];"
            # Overlay centered
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )
    else:
        # Simple: scale and pad with black bars
        filter_complex = (
            f"scale={REEL_WIDTH}:{REEL_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={REEL_WIDTH}:{REEL_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black"
        )

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-filter_complex", filter_complex,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        raise Exception(f"ffmpeg vertical conversion error: {result.stderr}")

    return output_path


def add_captions(
    video_path: str,
    output_path: str,
    captions: list,
    font_size: int = 22,
    font_color: str = "white",
    outline_color: str = "black",
    position: str = "bottom"
) -> str:
    """
    Burn captions into video using SRT subtitles (more robust than drawtext).

    Args:
        video_path: Path to source video
        output_path: Output file path
        captions: List of dicts with 'text', 'start', 'end' keys
        font_size: Caption font size
        font_color: Caption text color
        outline_color: Caption outline/border color
        position: 'top', 'center', or 'bottom'

    Returns:
        Path to captioned video
    """
    if not captions:
        # No captions, just copy
        shutil.copy(video_path, output_path)
        return output_path

    # Filter valid captions
    valid_captions = [c for c in captions if c.get("text", "").strip()]
    if not valid_captions:
        shutil.copy(video_path, output_path)
        return output_path

    # Create temporary SRT file
    srt_path = output_path.replace(".mp4", ".srt")

    try:
        # Write SRT file
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, caption in enumerate(valid_captions, 1):
                start = caption.get("start", 0)
                end = caption.get("end", start + 3)
                text = caption.get("text", "").strip()

                # Format timestamps as HH:MM:SS,mmm
                start_ts = format_srt_timestamp(start)
                end_ts = format_srt_timestamp(end)

                f.write(f"{i}\n")
                f.write(f"{start_ts} --> {end_ts}\n")
                f.write(f"{text}\n\n")

        # Position mapping for subtitles (MarginV - distance from bottom)
        margin_v = {
            "top": 450,
            "center": 250,
            "bottom": 50
        }.get(position, 50)

        # Use subtitles filter with styling
        # Escape path for ffmpeg filter (colons and backslashes)
        escaped_srt = srt_path.replace("\\", "/").replace(":", "\\:")

        # ASS/SSA color format is &HBBGGRR (BGR, not RGB)
        subtitle_filter = (
            f"subtitles='{escaped_srt}':"
            f"force_style='FontName=Arial,"
            f"FontSize={font_size},"
            f"PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,"
            f"BackColour=&H80000000,"
            f"BorderStyle=4,"
            f"Outline=1,"
            f"Shadow=0,"
            f"MarginV={margin_v},"
            f"MarginL=20,"
            f"MarginR=20,"
            f"Alignment=2'"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-vf", subtitle_filter,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            # Get meaningful error
            error_lines = [l for l in result.stderr.split('\n')
                         if l.strip() and 'version' not in l.lower()
                         and not l.startswith('  ') and 'built with' not in l.lower()
                         and 'configuration' not in l.lower() and 'lib' not in l.lower()]
            error_msg = '\n'.join(error_lines[-5:]) if error_lines else "Unknown ffmpeg error"
            raise Exception(f"ffmpeg subtitle error: {error_msg}")

        return output_path

    finally:
        # Cleanup SRT file
        if os.path.exists(srt_path):
            os.remove(srt_path)


def format_srt_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_captions_from_segments(
    segments: list,
    start_time: float,
    end_time: float,
    max_chars: int = 35
) -> list:
    """
    Generate caption entries from transcript segments for a clip.

    Args:
        segments: List of transcript segments with 'start', 'end', 'text'
        start_time: Clip start time
        end_time: Clip end time
        max_chars: Maximum characters per caption line

    Returns:
        List of caption dicts with adjusted timestamps
    """
    captions = []

    for seg in segments:
        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", seg_start + 2)

        # Check if segment overlaps with our clip
        if seg_end < start_time or seg_start > end_time:
            continue

        # Adjust timestamps relative to clip start
        adj_start = max(0, seg_start - start_time)
        adj_end = min(end_time - start_time, seg_end - start_time)

        text = seg.get("text", "").strip()

        # Split long text into multiple lines
        if len(text) > max_chars:
            words = text.split()
            lines = []
            current_line = []
            current_len = 0

            for word in words:
                if current_len + len(word) + 1 > max_chars:
                    lines.append(" ".join(current_line))
                    current_line = [word]
                    current_len = len(word)
                else:
                    current_line.append(word)
                    current_len += len(word) + 1

            if current_line:
                lines.append(" ".join(current_line))

            # Distribute time across lines
            line_duration = (adj_end - adj_start) / len(lines)
            for i, line in enumerate(lines):
                captions.append({
                    "text": line,
                    "start": adj_start + (i * line_duration),
                    "end": adj_start + ((i + 1) * line_duration)
                })
        else:
            captions.append({
                "text": text,
                "start": adj_start,
                "end": adj_end
            })

    return captions


def create_reel(
    video_path: str,
    start_time: float,
    end_time: float,
    output_filename: str,
    segments: Optional[list] = None,
    include_captions: bool = True,
    blur_background: bool = True
) -> dict:
    """
    Complete pipeline to create an Instagram Reel from a video segment.

    Args:
        video_path: Path to source video
        start_time: Start time in seconds
        end_time: End time in seconds
        output_filename: Name for output file (without extension)
        segments: Transcript segments for captions
        include_captions: Whether to burn in captions
        blur_background: Whether to use blur background effect

    Returns:
        Dict with reel_path, duration, and metadata
    """
    duration = end_time - start_time

    # Validate duration for Instagram Reels (15-60 seconds)
    if duration < 5:
        raise ValueError("Reel must be at least 5 seconds")
    if duration > 60:
        raise ValueError("Reel cannot exceed 60 seconds")

    # Create temporary files for intermediate steps
    temp_dir = tempfile.mkdtemp()

    try:
        # Step 1: Extract clip
        clip_path = os.path.join(temp_dir, "clip.mp4")
        extract_clip(video_path, start_time, end_time, clip_path)

        # Step 2: Convert to vertical format
        vertical_path = os.path.join(temp_dir, "vertical.mp4")
        convert_to_vertical(clip_path, vertical_path, blur_background)

        # Step 3: Add captions if requested
        final_path = str(REELS_DIR / f"{output_filename}.mp4")

        if include_captions and segments:
            captions = generate_captions_from_segments(
                segments, start_time, end_time
            )
            add_captions(vertical_path, final_path, captions)
        else:
            shutil.move(vertical_path, final_path)

        return {
            "reel_path": final_path,
            "duration": duration,
            "start_time": start_time,
            "end_time": end_time,
            "has_captions": include_captions and bool(segments),
            "dimensions": f"{REEL_WIDTH}x{REEL_HEIGHT}"
        }

    finally:
        # Cleanup temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)


def cleanup_reel(reel_path: str):
    """Remove a generated reel file"""
    try:
        if reel_path and os.path.exists(reel_path):
            os.remove(reel_path)
    except Exception:
        pass


def cleanup_old_reels(max_age_hours: int = 1):
    """Remove reel files older than specified hours"""
    import time

    current_time = time.time()
    max_age_seconds = max_age_hours * 3600

    for reel_file in REELS_DIR.glob("*.mp4"):
        try:
            file_age = current_time - reel_file.stat().st_mtime
            if file_age > max_age_seconds:
                reel_file.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    # Test with a sample video
    print("Video Clipper Module")
    print(f"Reels output directory: {REELS_DIR}")

    # Example usage:
    # result = create_reel(
    #     video_path="/path/to/video.mp4",
    #     start_time=10.0,
    #     end_time=30.0,
    #     output_filename="test_reel",
    #     segments=[{"start": 10, "end": 15, "text": "Hello world"}],
    #     include_captions=True
    # )
    # print(f"Reel created: {result['reel_path']}")
