# Audio Stream Detection Daemon - Installation Guide

## Overview

The Audio Stream Detection Daemon monitors your system for audio streams from applications like Microsoft Teams, YouTube, and custom patterns. When a matching stream is detected, it sends a desktop notification with a ready-to-use ffmpeg capture command.

## Features

- ✅ **Background monitoring** - Runs as a system service
- ✅ **Desktop notifications** - Modern notifications with copyable commands
- ✅ **Configurable detection** - Teams, YouTube, and custom patterns
- ✅ **Non-invasive** - Never modifies audio routing
- ✅ **User-friendly** - Simple CLI management

## Installation

### Prerequisites

- Linux system with PulseAudio or PipeWire
- Python 3.6+
- systemd (for service management)

### Quick Install

```bash
# Clone or download the audio-capture repository
cd /home/cgeng/work/myfiles/audio-capture

# Run the installation script
./install-daemon.sh
```

### Manual Installation

1. **Create directories:**
```bash
mkdir -p ~/.config/audio-detect
mkdir -p ~/.local/share/audio-detect
mkdir -p ~/AudioCaptures
```

2. **Install Python dependencies:**
```bash
pip3 install --user pyyaml pyperclip
```

3. **Install system dependencies:**
```bash
sudo apt-get install libnotify-bin
```

4. **Install systemd service:**
```bash
# Copy service file and adapt for your user
cp audio-detect-daemon.service ~/.config/systemd/user/
systemctl --user daemon-reload
```

## Configuration

### Default Configuration

The daemon creates a default configuration file at:
`~/.config/audio-detect/config.yaml`

```yaml
detection:
  poll_interval: 2  # Check every 2 seconds
  cooldown: 30      # Wait 30s before notifying same stream again

targets:
  teams:
    enabled: true
    patterns:
      - "microsoft teams"
      - "teams.microsoft.com"
      - "teams meeting"
      - "microsoft teams meeting"
  
  youtube:
    enabled: true
    patterns:
      - "youtube"
      - "youtu.be"
  
  custom:
    enabled: false
    patterns: []

paths:
  download_dir: "~/AudioCaptures"
  config_dir: "~/.config/audio-detect"
  log_dir: "~/.local/share/audio-detect"

organization:
  create_subdirs: true  # Create teams/, youtube/, custom/ subdirs
  filename_template: "{type}_{timestamp}.wav"

notification:
  method: "desktop"
  auto_copy: true      # Copy command to clipboard
  timeout: 10          # Notification display time (seconds)
  title: "🎤 Audio Stream Detected"
```

### Editing Configuration

```bash
# Open configuration in your default editor
audio-detect-service config

# Or edit directly
nano ~/.config/audio-detect/config.yaml
```

### Custom Patterns

Add your own detection patterns in the `custom` section:

```yaml
targets:
  custom:
    enabled: true
    patterns:
      - "spotify"           # Spotify music
      - "zoom"              # Zoom meetings
      - "vlc"               # VLC media player
      - "discord"           # Discord voice/chat
```

## Usage

### Basic Commands

```bash
# Start the daemon
audio-detect-service start

# Check status
audio-detect-service status

# View logs (live)
audio-detect-service logs

# Stop the daemon
audio-detect-service stop
```

### Auto-start on Login

```bash
# Enable automatic start when you log in
audio-detect-service enable

# Disable automatic start
audio-detect-service disable
```

### Testing

```bash
# Test daemon without starting service (dry run)
audio-detect-service test

# Or run directly
audio_detect_daemon --dry-run
```

## How It Works

### Detection Process

1. **Polling**: Daemon checks audio streams every 2 seconds (configurable)
2. **Classification**: Matches streams against enabled patterns (Teams, YouTube, custom)
3. **Notification**: Sends desktop notification with ffmpeg command
4. **Cooldown**: Waits 30 seconds before notifying same stream again

### Notification Format

When a matching stream is detected, you'll see:

```
🎤 Audio Stream Detected
Microsoft Teams - Weekly Standup

ffmpeg -f pulse -i alsa_output.usb-XYZ.monitor -ac 1 -ar 16000 teams_20250205_143000.wav
```

The ffmpeg command is automatically copied to your clipboard (if `pyperclip` is installed).

### File Organization

Captured files are organized in subdirectories:

```
~/AudioCaptures/
├── teams/
│   ├── teams_20250205_143000.wav
│   └── teams_20250205_151500.wav
├── youtube/
│   └── youtube_20250205_144500.wav
└── custom/
    └── custom_20250205_160000.wav
```

## Troubleshooting

### Common Issues

**Daemon not starting:**
```bash
# Check status for errors
audio-detect-service status

# View logs
audio-detect-service logs
```

**No notifications:**
```bash
# Test notification system
notify-send "Test" "This is a test notification"

# Install libnotify-bin if missing
sudo apt-get install libnotify-bin
```

**Audio streams not detected:**
```bash
# Check what audio streams are available
uv run audio-detect list

# Test with dry run
audio-detect-service test
```

**Permission issues:**
```bash
# Ensure directories exist and have correct permissions
ls -la ~/.config/audio-detect/
ls -la ~/.local/share/audio-detect/
ls -la ~/AudioCaptures/
```

### Debug Mode

For detailed debugging, run the daemon manually:

```bash
# Run with verbose output
audio_detect_daemon --config ~/.config/audio-detect/config.yaml
```

### Log Analysis

View detailed logs with journalctl:

```bash
# Show recent logs
journalctl --user -u audio-detect-daemon -n 50

# Follow logs live
journalctl --user -u audio-detect-daemon -f

# Show logs with timestamps
journalctl --user -u audio-detect-daemon --since "1 hour ago"
```

## Uninstallation

To completely remove the daemon:

```bash
# Stop and disable service
audio-detect-service stop
audio-detect-service disable

# Remove service file
rm ~/.config/systemd/user/audio-detect-daemon.service
systemctl --user daemon-reload

# Remove configuration and data
rm -rf ~/.config/audio-detect
rm -rf ~/.local/share/audio-detect

# Remove CLI scripts
rm ~/.local/bin/audio_detect_daemon
rm ~/.local/bin/audio-detect-service

# Optionally remove captured audio
rm -rf ~/AudioCaptures
```

## Advanced Configuration

### Environment Variables

The service sets these environment variables for audio access:

- `PULSE_RUNTIME_PATH` - PulseAudio runtime path
- `PULSE_SERVER` - PulseAudio server address
- `DISPLAY` - X11 display
- `DBUS_SESSION_BUS_ADDRESS` - D-Bus session bus

### Multiple Users

Each user has their own instance of the daemon with separate:
- Configuration files
- Audio captures
- Service instances

### Performance Tuning

Adjust polling and cooldown settings for your needs:

```yaml
detection:
  poll_interval: 1   # Faster detection (more CPU usage)
  cooldown: 60       # Longer cooldown (fewer notifications)
```

## Security Considerations

- Daemon runs as your user, not as root
- Only reads audio stream information (no modification)
- Configuration files are user-readable only
- No network access required

## Support

For issues or questions:

1. Check the logs: `audio-detect-service logs`
2. Test with dry run: `audio-detect-service test`
3. Verify configuration: `audio-detect-service config`
4. Check system audio: `uv run audio-detect status`
