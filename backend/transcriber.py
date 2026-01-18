"""Audio transcription using MLX Whisper (optimized for Apple Silicon)"""
import mlx_whisper


def transcribe_audio(audio_path: str, model_name: str = "mlx-community/whisper-large-v3-turbo") -> dict:
    """
    Transcribe audio file using MLX Whisper.

    Args:
        audio_path: Path to audio file
        model_name: Whisper model to use (default: large-v3-turbo for best speed/quality)

    Returns:
        dict with 'text' (full transcript) and 'segments' (timestamped chunks)
    """
    result = mlx_whisper.transcribe(
        audio_path,
        path_or_hf_repo=model_name,
        verbose=False
    )

    # Format segments with timestamps
    formatted_segments = []
    for segment in result.get("segments", []):
        formatted_segments.append({
            "start": segment["start"],
            "end": segment["end"],
            "text": segment["text"].strip()
        })

    return {
        "text": result["text"],
        "segments": formatted_segments,
        "language": result.get("language", "en")
    }


def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def segments_to_text_with_timestamps(segments: list) -> str:
    """Convert segments to readable text with timestamps"""
    lines = []
    for seg in segments:
        timestamp = format_timestamp(seg["start"])
        lines.append(f"[{timestamp}] {seg['text']}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = transcribe_audio(sys.argv[1])
        print(f"Language: {result['language']}")
        print(f"Segments: {len(result['segments'])}")
        print(f"\nTranscript:\n{result['text'][:500]}...")
