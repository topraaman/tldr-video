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


async def translate_text(
    text: str,
    source_lang: str,
    target_lang: str,
    model: str = DEFAULT_MODEL
) -> dict:
    """
    Translate text between languages while preserving formatting.
    Processes in chunks to handle long texts.

    Args:
        text: Text to translate
        source_lang: Source language code ('en', 'ta', etc.)
        target_lang: Target language code
        model: Ollama model to use

    Returns:
        dict with 'translated_text' and 'segments' if available
    """
    LANG_NAMES = {
        "en": "English",
        "ta": "Tamil",
        "hi": "Hindi",
        "te": "Telugu",
        "kn": "Kannada",
        "ml": "Malayalam"
    }

    source_name = LANG_NAMES.get(source_lang, source_lang)
    target_name = LANG_NAMES.get(target_lang, target_lang)

    # Split into chunks for processing
    CHUNK_SIZE = 2000
    chunks = []
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

    translated_parts = []

    async with httpx.AsyncClient(timeout=180.0) as client:
        for i, chunk in enumerate(chunks):
            prompt = f"""Translate the following text from {source_name} to {target_name}.

Rules:
1. Preserve all formatting including **bold** markers
2. Keep section headings formatted as **Heading**
3. Maintain paragraph structure
4. Translate naturally, not word-by-word
5. Keep proper nouns and technical terms as appropriate
6. Output ONLY the translation, no explanations

Text to translate:
{chunk}

{target_name} translation:"""

            response = await client.post(
                OLLAMA_URL,
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 3000
                    }
                }
            )

            if response.status_code == 200:
                result = response.json()
                translated = result.get("response", chunk)
                translated_parts.append(translated)
            else:
                translated_parts.append(chunk)

    full_translation = "\n\n".join(translated_parts)

    return {
        "translated_text": full_translation,
        "source_lang": source_lang,
        "target_lang": target_lang
    }


async def identify_reel_segments(
    transcript: str,
    segments: list,
    title: str = "",
    model: str = DEFAULT_MODEL
) -> dict:
    """
    Analyze transcript to identify the most engaging 15-30 second segments
    suitable for Instagram Reels.

    Looks for: hooks, humor, insights, emotional moments, quotable content.

    Args:
        transcript: Full transcript text
        segments: List of transcript segments with timestamps
        title: Video title
        model: Ollama model to use

    Returns:
        dict with 'reel_segments' list containing:
        - start_time: float (seconds)
        - end_time: float (seconds)
        - title: str (catchy reel title)
        - hook_score: float (0-1 engagement score)
        - hook_reason: str (why this segment is engaging)
    """
    # Build context with timestamps
    timestamped_text = ""
    for seg in segments[:150]:  # More segments for better coverage
        start_secs = seg.get("start", 0)
        mins = int(start_secs // 60)
        secs = int(start_secs % 60)
        timestamped_text += f"[{mins:02d}:{secs:02d}] {seg.get('text', '')}\n"

    prompt = f"""You are a social media expert analyzing video content for Instagram Reels potential.

Analyze this video transcript and identify the TOP 5 most engaging segments that would make great 15-30 second Reels. Look for:

1. **Strong hooks** - attention-grabbing statements that make people stop scrolling
2. **Emotional moments** - surprising, funny, inspiring, or relatable content
3. **Quotable insights** - memorable one-liners or wisdom
4. **Dramatic reveals** - plot twists, surprising facts, or "aha" moments
5. **Actionable tips** - quick advice that provides immediate value

For each segment:
- The segment MUST be between 15-30 seconds (check timestamps!)
- Choose segments that stand alone without needing prior context
- Prefer segments with complete thoughts/sentences

Video Title: {title}

Transcript with timestamps:
{timestamped_text[:10000]}

Respond in this exact JSON format:
{{
    "reel_segments": [
        {{
            "start_time": 45.0,
            "end_time": 65.0,
            "title": "Catchy Reel Title Here",
            "hook_score": 0.9,
            "hook_reason": "Strong opening hook with surprising statistic"
        }},
        {{
            "start_time": 120.0,
            "end_time": 145.0,
            "title": "Another Great Moment",
            "hook_score": 0.85,
            "hook_reason": "Emotional story that resonates with audience"
        }}
    ]
}}

Important:
- Start/end times must be in SECONDS (convert MM:SS to seconds)
- Each segment should be 15-30 seconds long
- hook_score is 0.0 to 1.0 (1.0 = most engaging)
- Return exactly 5 segments, ranked by hook_score (highest first)

JSON Response:"""

    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.4,
                    "num_predict": 2000
                }
            }
        )

        if response.status_code != 200:
            raise Exception(f"Ollama error: {response.text}")

        result = response.json()
        llm_response = result.get("response", "")

        # Parse JSON from response
        try:
            json_start = llm_response.find("{")
            json_end = llm_response.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                json_str = llm_response[json_start:json_end]
                parsed = json.loads(json_str)

                reel_segments = parsed.get("reel_segments", [])

                # Validate and clean segments
                validated_segments = []
                for seg in reel_segments:
                    start = float(seg.get("start_time", 0))
                    end = float(seg.get("end_time", start + 20))
                    duration = end - start

                    # Ensure valid duration (allow some flexibility: 10-45 seconds)
                    if 10 <= duration <= 45:
                        validated_segments.append({
                            "start_time": start,
                            "end_time": end,
                            "title": seg.get("title", "Untitled Clip"),
                            "hook_score": min(1.0, max(0.0, float(seg.get("hook_score", 0.5)))),
                            "hook_reason": seg.get("hook_reason", ""),
                            "source": "ai_suggested"
                        })

                # Sort by hook_score descending
                validated_segments.sort(key=lambda x: x["hook_score"], reverse=True)

                return {
                    "reel_segments": validated_segments[:5]  # Top 5
                }

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            pass

        # Fallback: return empty list with error
        return {
            "reel_segments": [],
            "error": "Failed to parse LLM response",
            "raw_response": llm_response[:500]
        }


def segments_to_chapter_suggestions(chapters: list, segments: list) -> list:
    """
    Convert chapters to potential reel segments.
    Allows manual selection from existing chapters.

    Args:
        chapters: List of chapter dicts with timestamp and title
        segments: Transcript segments for duration calculation

    Returns:
        List of reel segment suggestions from chapters
    """
    reel_suggestions = []

    for i, chapter in enumerate(chapters):
        timestamp = chapter.get("timestamp", "00:00")

        # Parse timestamp to seconds
        parts = timestamp.split(":")
        if len(parts) == 2:
            start_secs = int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            start_secs = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        else:
            start_secs = 0

        # Estimate end time from next chapter or add 30 seconds
        if i + 1 < len(chapters):
            next_ts = chapters[i + 1].get("timestamp", "00:00")
            next_parts = next_ts.split(":")
            if len(next_parts) == 2:
                end_secs = int(next_parts[0]) * 60 + int(next_parts[1])
            elif len(next_parts) == 3:
                end_secs = int(next_parts[0]) * 3600 + int(next_parts[1]) * 60 + int(next_parts[2])
            else:
                end_secs = start_secs + 30
        else:
            end_secs = start_secs + 30

        # Limit to 30 seconds for reel suggestion
        if end_secs - start_secs > 30:
            end_secs = start_secs + 30

        reel_suggestions.append({
            "start_time": float(start_secs),
            "end_time": float(end_secs),
            "title": chapter.get("title", f"Chapter {i + 1}"),
            "hook_score": 0.5,  # Default score for chapters
            "hook_reason": "From video chapter",
            "source": "chapter"
        })

    return reel_suggestions


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
