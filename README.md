# Audio Capture & Transcription Systems

Three systems for audio processing on Linux:

## ⭐ System 1: Audio Stream Detection Service (NEW - Recommended)

**Background monitoring with desktop notifications for Teams, YouTube, and custom patterns.**

### Features

- **Background Monitoring**: Runs as system service, detects audio streams automatically
- **Desktop Notifications**: Modern notifications with ready-to-use ffmpeg commands
- **Configurable Patterns**: Teams, YouTube, and custom detection patterns
- **Non-Invasive**: Never modifies audio routing - read-only monitoring
- **Clipboard Integration**: Auto-copies ffmpeg commands to clipboard
- **Home Directory**: All files stored in user home directory (no sudo needed)

### Quick Start

```bash
# Clone and install
git clone https://github.com/ChristianGeng/audio-capture.git
cd audio-capture
./install-daemon.sh

# Start detection
audio-detect-service start

# Check status
audio-detect-service status

# Configure patterns
audio-detect-service config
```

### How It Works

1. **Daemon monitors** PulseAudio/PipeWire for audio streams every 2 seconds
2. **Pattern Matching** against Teams, YouTube, and custom patterns
3. **Desktop Notification** with ffmpeg command sent when match found
4. **Auto-Copy** command to clipboard for easy pasting
5. **Organized Storage** in `~/AudioCaptures/teams/`, `~/AudioCaptures/youtube/`, etc.

### Usage Examples

```bash
# Start/stop service
audio-detect-service start
audio-detect-service stop

# Enable auto-start on login
audio-detect-service enable

# View logs
audio-detect-service logs

# Test detection
audio-detect-service test

# Edit configuration
audio-detect-service config
```

### Configuration

Edit `~/.config/audio-detect/config.yaml`:

```yaml
targets:
  teams:
    enabled: true
    patterns:
      - "microsoft teams"
      - "teams.microsoft.com"
  youtube:
    enabled: true
    patterns:
      - "youtube"
  custom:
    enabled: true
    patterns:
      - "spotify"
      - "zoom"
```

### Installation with UVX

The service uses `uvx` to run directly from the GitHub repository:

```bash
# System will automatically use the latest version from main branch
systemctl --user start audio-detect-daemon
```

## ⭐ System 2: Automatic Teams Meeting Recorder (Legacy)

**Zero-intervention audio recording for Microsoft Teams meetings.**

### Features

- **Fully Automatic**: Detects Teams meetings and records with zero user intervention
- **No Manual Routing**: No pavucontrol, no GUI, no setup needed
- **Systemd Service**: Runs in background, starts on boot
- **Simple**: ~100 lines of Python vs 415 in manual systems
- **Extensible**: Future Chrome extension support for meeting metadata

### Quick Start

```bash
# Install
./install-recorder.sh

# Check status
sudo systemctl status teams-auto-recorder

# View logs
journalctl -u teams-auto-recorder -f

# View recordings
ls -lh /var/log/teams-audio/
```

### How It Works

1. **Daemon monitors** PulseAudio for Teams audio streams
2. **Auto-detects** when Teams meeting starts
3. **Records** to `/var/log/teams-audio/meeting_YYYY-MM-DD_HH-MM-SS.wav`
4. **Stops** automatically 30 seconds after meeting ends
5. **Runs forever** as systemd service

### Post-Processing (Optional)

```bash
# Transcribe all recordings
python process_recordings.py

# Transcripts saved as .txt files
cat /var/log/teams-audio/meeting_*.txt
```

### Architecture

See [ADR-0001](docs/adr/0001-simplify-teams-audio-capture.md) for design decisions.

**Future Extension**: Chrome extension will add meeting metadata (title, participants, chat) without modifying audio recording code.

---

## 🎯 System 2: Chrome Tab Diarization & Transcription

Capture audio from a **specific Chrome tab**, identify speakers, and create speaker-attributed transcripts.


### Features

- **Chrome Tab Isolation**: Capture audio from specific Chrome tabs (not system-wide)
- **Speaker Diarization**: Identify who spoke when using pyannote.audio
- **Speaker-Attributed Transcripts**: Output showing "SPEAKER_01: Hello..." etc.
- **PulseAudio Integration**: Uses virtual sinks for audio routing


### Setup

1. **Install dependencies**:
   ```bash
   uv sync  # Includes pyannote.audio, torch, etc.
   ```

2. **Set up HuggingFace token** (for pyannote models):
   ```bash
   export HUGGINGFACE_TOKEN=your_huggingface_token
   # Get token from: https://huggingface.co/settings/tokens
   ```


### Usage

#### Complete Workflow (Recommended)

```bash
# One-command setup, capture, and process
python chrome_tab_diarizer.py workflow --duration 60
```

#### Step-by-Step Usage

```bash
# 1. Set up virtual sink for Chrome tab isolation
python chrome_tab_diarizer.py setup

# 2. Manually route Chrome audio in pavucontrol, then capture
python chrome_tab_diarizer.py capture --duration 30

# 3. Process captured audio with diarization
python chrome_tab_diarizer.py process path/to/audio.wav
```


### How It Works

1. **Virtual Sink Creation**: Creates a PulseAudio virtual sink for Chrome tab isolation
2. **Audio Routing**: Use `pavucontrol` to route specific Chrome tab audio to the virtual sink
3. **Capture**: Record audio from the virtual sink monitor
4. **Diarization**: Use pyannote.audio to identify speakers and timestamps
5. **Transcription**: Use Whisper MCP to transcribe the audio
6. **Combination**: Merge transcription with diarization for speaker-attributed output


### Requirements

- **HuggingFace Token**: For pyannote speaker diarization models
- **PulseAudio**: For virtual sink audio routing
- **pavucontrol**: GUI tool for audio routing (`sudo apt install pavucontrol`)


### Output Format

```text
🎤 Chrome Tab Audio Analysis Complete!
File: chrome_tab_capture_1234567890.wav
Transcription: 2456 chars
Speakers detected: 2

📝 Speaker-Attributed Transcript:

**SPEAKER_01:** Hello, welcome to our meeting today.

**SPEAKER_02:** Thank you for joining. Let's discuss the project timeline.

**SPEAKER_01:** I think we should focus on the key deliverables first...
```


---

## 🎤 System 3: Real-time Audio Streaming (Original)

The original real-time streaming system for continuous transcription.


### Features

- **Real-time streaming**: Continuous transcription without file saving
- **Low latency**: ~2 second delay from speech to text
- **Thread-safe**: Concurrent audio capture and transcription


### Usage

```bash
# Start real-time transcription
audio-stream start --chunk-duration 3 --overlap 0.5
```


---

## Choosing the Right System

| Use Case | Recommended System |
|----------|--------------------|
| **Background monitoring with notifications** | ⭐ Audio Stream Detection Service (System 1) |
| **Zero-intervention background recording** | ⭐ Teams Auto-Recorder (System 2) |
| **Manual tab isolation + diarization** | Chrome Tab Diarizer (System 3) |
| **Live meetings** needing real-time transcription | Real-time Streaming (System 4) |
| **Podcasts/Interviews** from browser | Chrome Tab Diarization (System 3) |
| **Research interviews** needing attribution | Chrome Tab Diarization (System 3) |


## Common Issues

### Chrome Tab Audio Not Capturing

1. Run `python chrome_tab_diarizer.py setup` to create virtual sink
2. Open `pavucontrol` → Playback tab
3. Find your Chrome tab → Change output to "Chrome_Tab_Audio"
4. Start playing audio in Chrome tab

### Diarization Fails

1. Set `HUGGINGFACE_TOKEN` environment variable
2. Ensure internet connection (models download ~500MB)
3. Falls back to placeholder diarization if models unavailable

### Audio Quality Issues

- Use 16kHz sample rate for better diarization
- Ensure Chrome tab is the only audio source in virtual sink
- Close other applications using the virtual sink
