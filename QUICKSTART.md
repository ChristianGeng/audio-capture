# Teams Auto-Recorder: Quick Start

Get automatic Teams meeting recording working in 5 minutes.

## Installation (One-Time Setup)

```bash
# Clone or navigate to repository
cd /home/cgeng/work/myfiles/audio-capture

# Run installation script
./install-recorder.sh

# Answer 'y' when prompted to start service
```

## Verify It's Working

```bash
# Check service status
sudo systemctl status teams-auto-recorder

# Should show: "active (running)"

# Watch live logs
journalctl -u teams-auto-recorder -f
```

## Test With a Meeting

1. Join a Teams meeting (or play audio in Teams)
2. Watch the logs - should see within 2 seconds:
   ```
   [HH:MM:SS] Started recording: /var/log/teams-audio/meeting_2024-02-04_10-30-00.wav
   ```
3. Leave the meeting
4. Wait 30 seconds - should see:
   ```
   [HH:MM:SS] Stopped recording: meeting_2024-02-04_10-30-00
   ```

## View Recordings

```bash
# List all recordings
ls -lh /var/log/teams-audio/

# Play a recording
ffplay /var/log/teams-audio/meeting_*.wav

# Check file properties
ffprobe /var/log/teams-audio/meeting_*.wav
```

## Generate Transcripts (Optional)

```bash
# Process all recordings
python3 process_recordings.py

# View transcript
cat /var/log/teams-audio/meeting_*.txt
```

## Common Commands

```bash
# Start service
sudo systemctl start teams-auto-recorder

# Stop service
sudo systemctl stop teams-auto-recorder

# Restart service
sudo systemctl restart teams-auto-recorder

# Disable service (stop running on boot)
sudo systemctl disable teams-auto-recorder

# Enable service (run on boot)
sudo systemctl enable teams-auto-recorder

# View last 50 log lines
journalctl -u teams-auto-recorder -n 50

# Follow logs in real-time
journalctl -u teams-auto-recorder -f
```

## Troubleshooting

### "No recordings are being created"

Check if Teams audio is detected:
```bash
# While Teams is playing audio, run:
pactl list source-outputs | grep -i teams
```

If nothing appears, Teams audio isn't being captured by PulseAudio. Try:
1. Restart Teams
2. Ensure microphone is unmuted in Teams
3. Try the desktop app instead of web version

### "Service won't start"

Check the logs:
```bash
journalctl -u teams-auto-recorder -n 50
```

Common issues:
- Missing dependencies: Run `sudo apt install pulseaudio-utils ffmpeg python3`
- Permission issues: Run `sudo chown $USER:$USER /var/log/teams-audio`

### "Recordings are silent"

Test audio capture:
```bash
# Record 5 seconds of system audio
ffmpeg -f pulse -i default.monitor -t 5 test.wav

# Play the test file
ffplay test.wav
```

If test.wav is also silent, check your PulseAudio configuration.

## Files & Directories

| Path | Description |
|------|-------------|
| `/var/log/teams-audio/` | Recordings directory |
| `teams_auto_recorder.py` | Main Python script |
| `/etc/systemd/system/teams-auto-recorder.service` | Systemd service file |
| `docs/adr/0001-*.md` | Architecture decision record |
| `TESTING.md` | Comprehensive testing guide |

## What Happens Automatically

1. **On Boot**: Service starts automatically
2. **Teams Meeting**: Recording starts within 2 seconds
3. **Meeting Ends**: Recording stops after 30 second grace period
4. **Files**: Saved as `/var/log/teams-audio/meeting_YYYY-MM-DD_HH-MM-SS.wav`

## Next Steps

- Read `TESTING.md` for comprehensive test procedures
- Read `docs/adr/0001-simplify-teams-audio-capture.md` for architecture details
- Set up cron job for automatic transcript generation:
  ```bash
  crontab -e
  # Add: 0 18 * * * /usr/bin/python3 /path/to/process_recordings.py
  ```

## Support

For issues, check:
1. Service logs: `journalctl -u teams-auto-recorder -f`
2. PulseAudio: `pactl list source-outputs`
3. System: `systemctl status teams-auto-recorder`
