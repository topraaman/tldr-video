#!/bin/bash
# Video to Transcript - Startup Script

cd "$(dirname "$0")"

echo "🎬 Video to Transcript - Word 2003 Edition"
echo "==========================================="
echo ""

# Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "📡 Starting Ollama..."
    ollama serve &
    sleep 3
fi

echo "✅ Ollama is running"

# Activate virtual environment
source venv/bin/activate

echo "🚀 Starting server at http://localhost:8000"
echo ""
echo "Open your browser to: http://localhost:8000"
echo "Press Ctrl+C to stop"
echo ""

cd backend
python main.py
