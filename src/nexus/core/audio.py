"""
audio.py — Shared audio utilities for Nexus.
Provides universal Whisper transcription services for the local and remote interfaces.
"""
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def transcribe_audio(file_path: str) -> str:
    """Universal Whisper transcription for any audio file."""
    client = OpenAI()
    try:
        with open(file_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        return transcription.text
    except Exception as e:
        # In a real app, you'd want to log this properly
        print(f"Transcription failed: {e}")
        return ""
