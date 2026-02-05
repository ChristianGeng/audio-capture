# Audio Stream Transcriber - Agent Documentation

This document provides context for AI agents working with the real-time audio streaming transcription system.

## Project Overview

The audio stream transcriber captures audio from Chrome (or any application) in real-time using ffmpeg and streams it to a Whisper MCP server for live transcription. This enables real-time speech-to-text with ~2 second latency.

## Architecture

### Core Components

1. **Audio Capture (`stream_transcriber.py`)**
   - Uses ffmpeg to capture audio from PulseAudio devices
   - Outputs raw float32 audio data to stdout
   - Runs in a separate thread for non-blocking operation

2. **Audio Buffer (`audio_buffer.py`)**
   - Circular buffer implementation for chunked audio processing
   - Handles overlapping chunks to avoid missing speech at boundaries
   - Thread-safe with configurable chunk sizes

3. **MCP Client (`mcp_client.py`)**
   - Interfaces with the Whisper MCP server
   - Handles temporary file creation and cleanup
   - Supports both standard and enhanced transcription modes

4. **Configuration (`config.py`)**
   - Environment-based configuration using Pydantic
   - Handles audio device settings, chunk parameters, and API keys

5. **CLI Interface (`cli.py`)**
   - Typer-based command-line interface
   - Provides start, stop, and status commands

### Data Flow

```text
ffmpeg → Audio Buffer → MCP Client → Whisper API → Live Text Output
```

1. **Capture**: ffmpeg reads from PulseAudio device in real-time
2. **Buffer**: Audio is accumulated and chunked with overlap
3. **Transcribe**: Each chunk sent to Whisper MCP server
4. **Display**: Results shown with latency statistics

## Key Features

- **Real-time processing**: No need to wait for recording completion
- **Intelligent chunking**: Overlapping chunks prevent speech loss at boundaries
- **Thread-safe**: Concurrent audio capture and transcription
- **Configurable**: Adjustable chunk duration, overlap, and audio parameters
- **Rich output**: Beautiful terminal display with statistics

## Configuration

### Environment Variables

```env
OPENAI_API_KEY=your_key_here          # Required for Whisper
CHUNK_DURATION_SECONDS=5              # Audio chunk size
OVERLAP_SECONDS=1                     # Overlap between chunks
SAMPLE_RATE=16000                     # Audio sample rate
CHANNELS=1                           # Mono audio
PULSE_DEVICE=device_name             # PulseAudio monitor device
```

### Finding Audio Devices

Use `wpctl status` to identify the correct audio device:

1. Find default sink (marked with `*`) under "Sinks"
2. Use corresponding monitor device name from "Default Configured Node Names"

## Usage Patterns

### Basic Usage

```bash
audio-stream start                    # Start with default settings
audio-stream status                   # Show current configuration
```

### Custom Parameters

```bash
audio-stream start --chunk-duration 3 --overlap 0.5
```

### Development

```bash
python -m audio_stream_transcriber.cli start
```

## Performance Characteristics

- **Latency**: ~2 seconds from speech to transcription
- **Memory**: Efficient circular buffers (configurable max chunks)
- **CPU**: Low overhead, suitable for long sessions
- **Network**: Requires internet connection for OpenAI API

## Error Handling

The system includes comprehensive error handling for:

- Audio device connection issues
- MCP server communication failures
- Temporary file cleanup
- Graceful shutdown on SIGINT/SIGTERM

## Testing

### Basic Tests

```bash
python test_basic.py                 # Test core components
python demo.py                       # Interactive demo
```

### Audio Capture Test

The demo script includes a 5-second audio capture test to verify ffmpeg setup.

## Dependencies

- **ffmpeg**: Audio capture (system package)
- **mcp**: Model Context Protocol client
- **numpy**: Audio data processing
- **pydantic-settings**: Configuration management
- **typer**: CLI framework
- **rich**: Terminal formatting

## Troubleshooting Common Issues

### No Audio Capture

1. Verify device name with `wpctl status`
2. Check audio is playing to the correct sink
3. Test ffmpeg command manually

### MCP Connection Issues

1. Ensure MCP server is running
2. Verify OpenAI API key validity
3. Check network connectivity

### High Latency

1. Reduce chunk duration (3-4 seconds)
2. Reduce overlap (0.5 seconds)
3. Check internet connection speed

## Development Notes

- The system uses asyncio for concurrent operations
- Audio processing is handled in separate threads to avoid blocking
- Temporary files are automatically cleaned up after transcription
- The circular buffer prevents memory leaks during long sessions

## Future Enhancements

Potential improvements for agents to consider:

- Silence detection to avoid transcribing empty audio
- Audio level monitoring and visualization
- Multiple language support
- Local Whisper model integration
- Audio format conversion capabilities
- Real-time translation features
