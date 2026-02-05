#!/usr/bin/env python3
"""Process recorded Teams meetings with ASR.

This script processes recorded meeting audio files and generates transcripts
using the Whisper MCP server. Can be run manually or via cron.

Usage:
    python process_recordings.py [--recording-dir DIR]

Cron example (daily at 6 PM):
    0 18 * * * /path/to/venv/bin/python /path/to/process_recordings.py
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

try:
    import numpy as np
    import wave
    from audio_stream_transcriber.mcp_client import WhisperMCPClient
except ImportError as e:
    print(f"Error: Missing dependencies: {e}", file=sys.stderr)
    print("Install with: uv sync", file=sys.stderr)
    sys.exit(1)


async def process_recording(audio_file: Path, mcp_server_path: Path) -> dict:
    """Transcribe a recorded meeting.

    Args:
        audio_file: Path to WAV file
        mcp_server_path: Path to MCP server directory

    Returns:
        Transcription result dictionary
    """
    print(f"Processing: {audio_file.name}")

    # Load audio
    with wave.open(str(audio_file), 'rb') as wav:
        audio_data = np.frombuffer(
            wav.readframes(-1),
            dtype=np.int16
        ).astype(np.float32) / 32767

    # Transcribe
    client = WhisperMCPClient(server_path=mcp_server_path)
    await client.connect()

    try:
        result = await client.transcribe_audio(
            audio_data=audio_data,
            sample_rate=16000
        )

        # Save transcript as text
        transcript_file = audio_file.with_suffix('.txt')
        with open(transcript_file, 'w') as f:
            f.write(result['text'])

        print(f"  ✓ Saved transcript: {transcript_file.name}")

        # Save full result as JSON
        json_file = audio_file.with_suffix('.transcript.json')
        with open(json_file, 'w') as f:
            json.dump(result, f, indent=2)

        return result

    finally:
        await client.disconnect()


async def process_all_recordings(
    recording_dir: Path,
    mcp_server_path: Path,
    force: bool = False
):
    """Process all unprocessed recordings in directory.

    Args:
        recording_dir: Directory containing WAV files
        mcp_server_path: Path to MCP server
        force: If True, reprocess even if transcript exists
    """
    wav_files = sorted(recording_dir.glob("meeting_*.wav"))

    if not wav_files:
        print(f"No recordings found in {recording_dir}")
        return

    print(f"Found {len(wav_files)} recording(s)")
    print()

    processed_count = 0
    skipped_count = 0

    for wav_file in wav_files:
        transcript_file = wav_file.with_suffix('.txt')

        if transcript_file.exists() and not force:
            print(f"Skipping {wav_file.name} (transcript exists)")
            skipped_count += 1
            continue

        try:
            await process_recording(wav_file, mcp_server_path)
            processed_count += 1
        except Exception as e:
            print(f"  ✗ Error processing {wav_file.name}: {e}", file=sys.stderr)

        print()

    print(f"Summary: {processed_count} processed, {skipped_count} skipped")


def main():
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Process recorded Teams meetings with ASR"
    )
    parser.add_argument(
        '--recording-dir',
        type=Path,
        default=Path('/var/log/teams-audio'),
        help='Directory containing recordings (default: /var/log/teams-audio)'
    )
    parser.add_argument(
        '--mcp-server',
        type=Path,
        default=Path.cwd() / 'mcp-server-whisper',
        help='Path to MCP server directory (default: ./mcp-server-whisper)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Reprocess recordings even if transcripts exist'
    )

    args = parser.parse_args()

    # Validate directories
    if not args.recording_dir.exists():
        print(f"Error: Recording directory not found: {args.recording_dir}", file=sys.stderr)
        sys.exit(1)

    if not args.mcp_server.exists():
        print(f"Error: MCP server not found: {args.mcp_server}", file=sys.stderr)
        sys.exit(1)

    # Process recordings
    asyncio.run(process_all_recordings(
        args.recording_dir,
        args.mcp_server,
        args.force
    ))


if __name__ == "__main__":
    main()
