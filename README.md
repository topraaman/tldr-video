# TLDR.video

> **For people who hate videos that should've been text posts.**

Convert YouTube videos and podcasts into clean, formatted transcripts with auto-generated chapters and key takeaways. Features a nostalgic Microsoft Word 2003-inspired interface.

![Word 2003 Style UI](https://img.shields.io/badge/UI-Word%202003%20Style-blue)
![100% Local](https://img.shields.io/badge/Privacy-100%25%20Local-green)
![Zero Cost](https://img.shields.io/badge/Cost-$0%20per%20transcript-brightgreen)

## Features

- **Video to Text** - Paste any YouTube or podcast URL, get a clean transcript
- **Auto Chapters** - AI-generated chapter markers with timestamps
- **Key Takeaways** - Extracted insights and action items
- **Promo Removal** - Automatically removes "subscribe", "like", sponsor segments
- **Word 2003 UI** - Classic toolbar, formatting options, ruler, and status bar
- **Rich Editing** - Bold, italic, underline, highlight colors, font controls
- **Export Options** - Save as PDF or DOCX with thumbnail and formatting
- **Thumbnail Extraction** - Download video thumbnails for reference
- **100% Local** - Runs entirely on your machine, no API costs

## How It Works

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   YouTube URL   │ ──► │    yt-dlp       │ ──► │   Audio (MP3)   │
└─────────────────┘     │  (download)     │     └────────┬────────┘
                        └─────────────────┘              │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Formatted Doc  │ ◄── │   Llama 3.1     │ ◄── │  MLX Whisper    │
│  (PDF/DOCX)     │     │  (chapters &    │     │  (transcribe)   │
└─────────────────┘     │   formatting)   │     └─────────────────┘
                        └─────────────────┘
```

### Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Backend | FastAPI (Python) | API server |
| Transcription | MLX Whisper | Speech-to-text (Apple Silicon optimized) |
| LLM | Ollama + Llama 3.1 | Chapters, takeaways, formatting |
| Audio Download | yt-dlp | YouTube/podcast extraction |
| PDF Export | WeasyPrint | PDF generation |
| DOCX Export | python-docx | Word document generation |
| Frontend | Vanilla HTML/CSS/JS | Word 2003-style UI |

## Requirements

- **macOS with Apple Silicon** (M1/M2/M3/M4) - for MLX Whisper acceleration
- **Python 3.10+**
- **Homebrew**
- **~10GB disk space** (for Whisper and Llama models)

## Installation

### 1. Install System Dependencies

```bash
# Install Homebrew if not installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Ollama and Deno
brew install ollama deno

# Pull Llama 3.1 model (~5GB)
ollama pull llama3.1
```

### 2. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/tldr-video.git
cd tldr-video

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r backend/requirements.txt
```

### 3. First Run (Downloads Whisper Model)

```bash
# Start Ollama server (in a separate terminal)
ollama serve

# Start the application
./start.sh
```

The first transcription will download the Whisper model (~1.5GB). Subsequent runs are faster.

## Usage

### Quick Start

```bash
./start.sh
# Open http://localhost:8000 in your browser
```

### Manual Start

```bash
# Terminal 1: Start Ollama
ollama serve

# Terminal 2: Start the app
source venv/bin/activate
cd backend
python main.py
```

### Using the App

1. **Paste URL** - Enter a YouTube or podcast URL in the toolbar
2. **Click Transcribe** - Wait for processing (progress shown)
3. **Edit** - Use the Word-style editor to refine the transcript
4. **Format** - Apply bold, italic, highlights, change fonts
5. **Export** - Save as PDF or DOCX (includes thumbnail)

## Project Structure

```
tldr-video/
├── backend/
│   ├── main.py              # FastAPI server & API endpoints
│   ├── transcriber.py       # MLX Whisper transcription
│   ├── youtube_handler.py   # yt-dlp audio/thumbnail extraction
│   ├── llm_processor.py     # Ollama/Llama chapter generation
│   ├── exporters.py         # PDF & DOCX export
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── index.html           # Word 2003-style UI
│   ├── styles.css           # Classic silver/blue theme
│   └── app.js               # Editor & API interactions
├── downloads/               # Temporary audio/thumbnail files
├── start.sh                 # Startup script
└── README.md
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serve frontend |
| `/api/health` | GET | Check server status |
| `/api/transcribe` | POST | Start transcription job |
| `/api/job/{id}` | GET | Get job status/result |
| `/api/export` | POST | Export to PDF/DOCX |
| `/api/thumbnail/{file}` | GET | Download thumbnail |
| `/api/regenerate-chapters` | POST | Regenerate chapters/takeaways |

## Configuration

### Whisper Model

Edit `backend/transcriber.py` to change the model:

```python
# Options: whisper-tiny, whisper-base, whisper-small, whisper-medium, whisper-large-v3-turbo
model_name = "mlx-community/whisper-large-v3-turbo"  # Best quality
```

### LLM Model

Edit `backend/llm_processor.py` to use a different Ollama model:

```python
DEFAULT_MODEL = "llama3.1:latest"  # Or: mistral, qwen2.5, etc.
```

## Troubleshooting

### "Ollama not running"
```bash
ollama serve  # Start in a separate terminal
```

### Transcription stuck at "Downloading"
```bash
# Check if yt-dlp works
yt-dlp --version

# Update yt-dlp if needed
pip install -U yt-dlp
```

### Slow transcription
- First run downloads Whisper model (~1.5GB)
- Ensure Ollama is running for chapter generation
- Check Activity Monitor for GPU usage

### Port already in use
```bash
# Kill existing process
pkill -f "uvicorn main:app"
```

## Performance

| Video Length | Transcription Time* | LLM Processing |
|--------------|---------------------|----------------|
| 5 min | ~30 sec | ~20 sec |
| 15 min | ~1.5 min | ~45 sec |
| 60 min | ~5 min | ~2 min |

*On M4 Pro with 48GB RAM

## Contributing

Pull requests welcome! Areas for improvement:

- [ ] SponsorBlock integration (skip sponsor segments)
- [ ] Multiple language support
- [ ] Batch processing
- [ ] Chrome extension version
- [ ] Speaker diarization

## License

MIT License - feel free to use, modify, and distribute.

## Acknowledgments

- [MLX Whisper](https://github.com/ml-explore/mlx-examples) - Apple Silicon optimized transcription
- [Ollama](https://ollama.ai/) - Local LLM runner
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Video/audio downloader
- Microsoft Word 2003 - UI inspiration

---

**Made for people who believe most videos should've been blog posts.**
