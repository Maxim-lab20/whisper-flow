#!/bin/bash

# Quick development setup script

set -e

echo "🚀 Whisper Transcription Pipeline - Quick Start"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.11+ first."
    exit 1
fi

# Check if ffmpeg is installed
if ! command -v ffmpeg &> /dev/null; then
    echo "❌ ffmpeg is not installed. Please install ffmpeg first."
    echo "   On macOS: brew install ffmpeg"
    echo "   On Ubuntu: sudo apt-get install ffmpeg"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create storage directories
echo "📁 Creating storage directories..."
mkdir -p storage/audio
mkdir -p storage/models

# Copy .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file..."
    cp .env.example .env
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "To start the application, choose one of the following:"
echo ""
echo "1. Docker (recommended):"
echo "   docker-compose up -d"
echo ""
echo "2. Manual start (requires Redis):"
echo "   # Terminal 1 - Start API server:"
echo "   source venv/bin/activate"
echo "   uvicorn app.main:app --reload"
echo ""
echo "   # Terminal 2 - Start worker:"
echo "   source venv/bin/activate"
echo "   python -m app.workers.transcription_worker"
echo ""
echo "API will be available at: http://localhost:8000"
echo "API docs: http://localhost:8000/docs"
