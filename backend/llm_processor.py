"""LLM processing using Ollama for chapters and takeaways generation"""
import httpx
import json

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "llama3.1:latest"


async def generate_chapters_and_takeaways(
    transcript: str,
    segments: list,
    title: str = "",
    model: str = DEFAULT_MODEL
) -> dict:
    """
    Generate chapters and key takeaways from transcript using local LLM.

    Returns:
        dict with 'chapters' and 'takeaways'
    """
    # Build context with timestamps
    timestamped_text = ""
    for seg in segments[:100]:  # Limit to avoid token overflow
        mins = int(seg["start"] // 60)
        secs = int(seg["start"] % 60)
        timestamped_text += f"[{mins:02d}:{secs:02d}] {seg['text']}\n"

    prompt = f"""Analyze this video/podcast transcript and generate:
1. CHAPTERS: Identify 4-8 logical chapters/sections with timestamps. Format each as:
   [MM:SS] Chapter Title

2. KEY TAKEAWAYS: Extract 5-10 most important points, insights, or actionable items.

Title: {title}

Transcript with timestamps:
{timestamped_text[:8000]}

Respond in this exact JSON format:
{{
    "chapters": [
        {{"timestamp": "00:00", "title": "Introduction"}},
        {{"timestamp": "02:30", "title": "Main Topic"}}
    ],
    "takeaways": [
        "First key insight or takeaway",
        "Second key insight or takeaway"
    ]
}}

JSON Response:"""

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 1500
                }
            }
        )

        if response.status_code != 200:
            raise Exception(f"Ollama error: {response.text}")

        result = response.json()
        llm_response = result.get("response", "")

        # Parse JSON from response
        try:
            # Find JSON in response
            json_start = llm_response.find("{")
            json_end = llm_response.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                json_str = llm_response[json_start:json_end]
                parsed = json.loads(json_str)
                return {
                    "chapters": parsed.get("chapters", []),
                    "takeaways": parsed.get("takeaways", [])
                }
        except json.JSONDecodeError:
            pass

        # Fallback: return raw response for manual parsing
        return {
            "chapters": [{"timestamp": "00:00", "title": "Full Content"}],
            "takeaways": ["See transcript for details"],
            "raw_response": llm_response
        }


async def format_transcript_with_sections(
    text: str,
    chapters: list,
    model: str = DEFAULT_MODEL
) -> str:
    """
    Format transcript into sections with bold headings.
    Removes promotional content (subscribe, sponsors, ads mentions).
    Processes in chunks to handle long transcripts.
    """
    CHUNK_SIZE = 4000  # Characters per chunk
    chunks = []

    # Split text into manageable chunks
    words = text.split()
    current_chunk = []
    current_length = 0

    for word in words:
        if current_length + len(word) + 1 > CHUNK_SIZE:
            chunks.append(' '.join(current_chunk))
            current_chunk = [word]
            current_length = len(word)
        else:
            current_chunk.append(word)
            current_length += len(word) + 1

    if current_chunk:
        chunks.append(' '.join(current_chunk))

    formatted_parts = []

    async with httpx.AsyncClient(timeout=180.0) as client:
        for i, chunk in enumerate(chunks):
            prompt = f"""Format this transcript section for readability. You must:

1. REMOVE any mentions of:
   - Subscribing to channel
   - Liking the video
   - Hitting the bell/notification
   - Sponsor segments or ad reads
   - Patreon/membership promotions
   - Social media follows
   - "Check out my other videos"
   - Any self-promotional content

2. ORGANIZE into logical paragraphs (3-5 sentences each)

3. ADD section headings where topics change. Format headings as: **Heading Title**

4. FIX grammar and remove filler words (um, uh, you know, like)

5. Keep all the actual educational/informational content intact

Transcript section {i+1}/{len(chunks)}:
{chunk}

Formatted output (with **bold** section headings):"""

            response = await client.post(
                OLLAMA_URL,
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.2,
                        "num_predict": 3000
                    }
                }
            )

            if response.status_code == 200:
                result = response.json()
                formatted_text = result.get("response", chunk)
                formatted_parts.append(formatted_text)
            else:
                # On error, use original chunk
                formatted_parts.append(chunk)

    # Combine all parts
    full_formatted = "\n\n".join(formatted_parts)

    return full_formatted


async def improve_transcript_grammar(
    text: str,
    model: str = DEFAULT_MODEL
) -> str:
    """
    Clean up transcript grammar and formatting while preserving meaning.
    DEPRECATED: Use format_transcript_with_sections instead.
    """
    prompt = f"""Clean up this transcript for readability. Fix grammar, punctuation, and remove filler words (um, uh, like) while preserving the original meaning exactly. Keep it natural and conversational.

Transcript:
{text[:6000]}

Cleaned transcript:"""

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 4000
                }
            }
        )

        if response.status_code != 200:
            return text  # Return original on error

        result = response.json()
        return result.get("response", text)


def check_ollama_running() -> bool:
    """Check if Ollama server is running"""
    try:
        response = httpx.get("http://localhost:11434/api/tags", timeout=5.0)
        return response.status_code == 200
    except Exception:
        return False


if __name__ == "__main__":
    import asyncio

    print(f"Ollama running: {check_ollama_running()}")

    # Test with sample transcript
    test_segments = [
        {"start": 0, "text": "Welcome to this tutorial about Python programming."},
        {"start": 30, "text": "Today we'll cover the basics of functions."},
        {"start": 60, "text": "Functions help you organize your code."},
    ]

    async def test():
        result = await generate_chapters_and_takeaways(
            "Test transcript",
            test_segments,
            "Python Tutorial"
        )
        print(json.dumps(result, indent=2))

    asyncio.run(test())
