"""
voice.py — Local voice interface for the Nexus Engine.
Captures microphone input and uses Whisper for hands-free vault queries.
"""
import sys
import wave
import pyaudio
import os
import tempfile
import threading
from dotenv import load_dotenv

from core.audio import transcribe_audio

# Load env variables (for OPENAI_API_KEY)
load_dotenv()

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100

def record_audio(filename):
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    
    print("🎙️  Press Enter to start recording...")
    input()
    
    print("🔴 Recording... (Press Enter to stop)")
    
    frames = []
    is_recording = True

    def capture_input():
        nonlocal is_recording
        input()
        is_recording = False

    # Start a thread to wait for the second Enter press
    input_thread = threading.Thread(target=capture_input)
    input_thread.start()

    while is_recording:
        data = stream.read(CHUNK)
        frames.append(data)
        
    print("⏹️  Stopped recording.")
    
    stream.stop_stream()
    stream.close()
    p.terminate()

    wf = wave.open(filename, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()

def capture_voice_query():
    # Force UTF-8 output
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    
    temp_dir = tempfile.gettempdir()
    audio_path = os.path.join(temp_dir, "brain_query.wav")
    
    try:
        record_audio(audio_path)
    except Exception as e:
        print(f"Audio capture failed: {e}")
        return None

    print("⏳ Transcribing with Whisper...")
    query = transcribe_audio(audio_path)
    
    if os.path.exists(audio_path):
        os.remove(audio_path)
            
    if not query or query.strip() == "":
        print("No speech detected.")
        return None
        
    return query

if __name__ == "__main__":
    query = capture_voice_query()
    if query:
        from agents.librarian.api import ask_librarian
        print(f"🧠 Querying Vault Agent: {query}")
        print("Agent is reasoning and searching the vault...\n")
        response = ask_librarian(query)
        print("\n" + "="*45)
        print("🤖 Response:")
        print("="*45)
        print(response)
        print("="*45 + "\n")
