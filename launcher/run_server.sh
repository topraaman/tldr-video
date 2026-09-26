#!/bin/bash
# Runs in Terminal: sets up the Python environment on first use, then starts
# the app via start.sh.

cd "$(dirname "$0")/.." || exit 1

if ! command -v ollama >/dev/null 2>&1; then
    echo "❌ Ollama is not installed. Run: brew install ollama && ollama pull llama3.1"
    exit 1
fi

# A virtual environment breaks if the project folder is moved; rebuild it then
if [ -d venv ] && ! grep -qF "$(pwd)/venv" venv/bin/activate 2>/dev/null; then
    echo "📦 Project folder was moved - rebuilding the Python environment..."
    rm -rf venv
fi

if [ ! -d venv ]; then
    echo "📦 First run: creating virtual environment and installing dependencies..."
    python3 -m venv venv && ./venv/bin/pip install -r backend/requirements.txt || {
        echo "❌ Dependency install failed."
        rm -rf venv
        exit 1
    }
fi

# Install new dependencies whenever requirements.txt changes (e.g. after git pull)
STAMP=venv/.requirements-installed
if [ ! -f "$STAMP" ] || [ backend/requirements.txt -nt "$STAMP" ]; then
    echo "📦 Installing updated dependencies..."
    if ./venv/bin/pip install -r backend/requirements.txt; then
        touch "$STAMP"
    else
        echo "⚠️  Some dependencies failed to install; starting anyway (AI features may be unavailable)."
    fi
fi

exec ./start.sh
