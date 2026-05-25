#!/usr/bin/env python3
"""
Example client for the Whisper Transcription API.

Usage:
    python example_client.py path/to/audio.wav
"""

import os
import sys
import time
import requests
from pathlib import Path


API_BASE_URL = "http://localhost:8000/api/v1"


def transcribe_file(file_path: str, language: str = None, model: str = "base") -> dict:
    """
    Transcribe an audio file.

    Args:
        file_path: Path to audio file
        language: Language code (auto-detect if None)
        model: Whisper model size

    Returns:
        Transcription result
    """
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    # Step 1: Upload and create job
    print(f"Uploading {file_path}...")

    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, "audio/wav")}
        data = {"model": model}
        if language:
            data["language"] = language

        response = requests.post(f"{API_BASE_URL}/transcribe", files=files, data=data)

    if response.status_code != 202:
        print(f"Error uploading file: {response.text}")
        sys.exit(1)

    job = response.json()
    job_id = job["job_id"]
    print(f"Job created: {job_id}")
    print(f"Status: {job['status']}")

    # Step 2: Poll for completion
    print("\nProcessing", end="", flush=True)

    while True:
        response = requests.get(f"{API_BASE_URL}/jobs/{job_id}")

        if response.status_code != 200:
            print(f"\nError checking job status: {response.text}")
            sys.exit(1)

        job = response.json()
        status = job["status"]

        if status == "completed":
            print(" ✓")
            break
        elif status == "failed":
            print(f" ✗\nError: {job.get('error', 'Unknown error')}")
            sys.exit(1)

        print(".", end="", flush=True)
        time.sleep(1)

    # Step 3: Display results
    print("\n" + "=" * 50)
    print("TRANSCRIPTION RESULT")
    print("=" * 50)

    result = job["result"]
    print(f"\nText: {result['text']}")
    print(f"Language: {result['language']}")
    print(f"Duration: {result['duration']:.2f}s")

    if result.get("segments"):
        print(f"\nSegments ({len(result['segments'])}):")
        for i, segment in enumerate(result["segments"], 1):
            print(f"  {i}. [{segment['start']:.2f}s - {segment['end']:.2f}s] {segment['text']}")

    if result.get("words"):
        print(f"\nWord timestamps ({len(result['words'])}):")
        for word in result["words"]:
            print(f"  [{word['start']:.2f}s - {word['end']:.2f}s] {word['word']}")

    print("\n" + "=" * 50)

    return job


def list_jobs():
    """List all jobs."""
    response = requests.get(f"{API_BASE_URL}/jobs")

    if response.status_code != 200:
        print(f"Error: {response.text}")
        return

    data = response.json()
    print(f"\nJobs (total: {data['total']}):")

    for job in data["jobs"]:
        print(f"  {job['job_id']}: {job['status']} ({job['created_at']})")


def health_check():
    """Check API health."""
    response = requests.get(f"{API_BASE_URL}/health")

    if response.status_code != 200:
        print(f"API unhealthy: {response.text}")
        return False

    data = response.json()
    print(f"API Status: {data['status']}")
    print(f"Version: {data['version']}")
    print(f"Workers: {data['workers']}")
    print(f"Queued jobs: {data['queued_jobs']}")

    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Whisper Transcription API Client")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Transcribe command
    transcribe_parser = subparsers.add_parser("transcribe", help="Transcribe an audio file")
    transcribe_parser.add_argument("file", help="Path to audio file")
    transcribe_parser.add_argument("--language", "-l", help="Language code")
    transcribe_parser.add_argument("--model", "-m", default="base", help="Whisper model size")

    # List command
    subparsers.add_parser("list", help="List all jobs")

    # Health command
    subparsers.add_parser("health", help="Check API health")

    args = parser.parse_args()

    if args.command == "transcribe":
        transcribe_file(args.file, args.language, args.model)
    elif args.command == "list":
        list_jobs()
    elif args.command == "health":
        health_check()
    else:
        parser.print_help()
