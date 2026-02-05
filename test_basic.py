#!/usr/bin/env python3
"""Basic test of the audio stream transcriber."""

import asyncio
import sys
from pathlib import Path

# Add the project to Python path
sys.path.insert(0, str(Path(__file__).parent))

from audio_stream_transcriber.config import get_settings
from audio_stream_transcriber.audio_buffer import AudioBuffer
import numpy as np


def test_audio_buffer():
    """Test the audio buffer functionality."""
    print("Testing audio buffer...")
    
    # Create buffer
    buffer = AudioBuffer(
        chunk_duration=2.0,
        overlap=0.5,
        sample_rate=16000,
        channels=1
    )
    
    # Add some test audio data
    chunk_samples = int(2.0 * 16000)  # 2 seconds at 16kHz
    test_audio = np.random.random(chunk_samples).astype(np.float32) * 0.1
    
    print(f"Adding {len(test_audio)} audio samples...")
    buffer.add_audio_data(test_audio)
    
    # Get status
    status = buffer.get_buffer_status()
    print(f"Buffer status: {status}")
    
    # Try to get a chunk
    chunk_data = buffer.get_next_chunk(timeout=1.0)
    if chunk_data:
        chunk, timestamp = chunk_data
        print(f"Got chunk with {len(chunk)} samples at timestamp {timestamp}")
    else:
        print("No chunk available")
    
    print("Audio buffer test completed!")


def test_config():
    """Test configuration loading."""
    print("Testing configuration...")
    
    try:
        settings = get_settings()
        print(f"Sample rate: {settings.sample_rate}")
        print(f"Chunk duration: {settings.chunk_duration_seconds}")
        print(f"Overlap: {settings.overlap_seconds}")
        print(f"Device: {settings.pulse_device}")
        print("Configuration test completed!")
    except Exception as e:
        print(f"Configuration error: {e}")


if __name__ == "__main__":
    print("Running basic tests...")
    
    test_config()
    print()
    test_audio_buffer()
    
    print("\nAll tests completed!")
