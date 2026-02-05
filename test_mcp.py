#!/usr/bin/env python3
"""Test MCP server connection."""

import asyncio
import sys
from pathlib import Path

# Add the project to Python path
sys.path.insert(0, str(Path(__file__).parent))

from audio_stream_transcriber.mcp_client import WhisperMCPClient


async def test_mcp_connection():
    """Test connecting to MCP server."""
    print("Testing MCP server connection...")
    
    client = WhisperMCPClient(
        server_path=Path(".") / "mcp-server-whisper"
    )
    
    try:
        await client.connect()
        print("✅ Connected to MCP server successfully!")
        
        # Test with a small dummy audio file
        import numpy as np
        dummy_audio = np.random.random(16000).astype(np.float32) * 0.1  # 1 second of silence
        
        print("Testing transcription with dummy audio...")
        result = await client.transcribe_audio(dummy_audio)
        print(f"✅ Transcription result: {result.get('text', 'No text')}")
        
    except Exception as e:
        print(f"❌ MCP connection failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await client.disconnect()
        print("Disconnected from MCP server")


if __name__ == "__main__":
    asyncio.run(test_mcp_connection())
