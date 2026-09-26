#!/bin/bash
# Runs in Terminal: sets up the Python environment on first use, then starts
# the app via start.sh.

cd "$(dirname "$0")/.." || exit 1

if ! command -v ollama >/dev/null 2>&1; then
    echo "❌ Ollama is not installed. Run: brew install ollama && ollama pull llama3.1"
    exit 1
fi

if [ ! -d venv ]; then
    echo "📦 First run: creating virtual environment and installing dependencies..."
    python3 -m venv venv && ./venv/bin/pip install -r backend/requirements.txt || {
        echo "❌ Dependency install failed."
        rm -rf venv
        exit 1
    }
fi

exec ./start.sh
