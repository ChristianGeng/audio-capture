# Testing Guide: Teams Auto-Recorder

This guide covers testing the automatic Teams meeting recorder.

## Prerequisites

```bash
# Check required commands are installed
command -v pactl && echo "✓ PulseAudio installed"
command -v ffmpeg && echo "✓ ffmpeg installed"
command -v python3 && echo "✓ Python installed"
command -v systemctl && echo "✓ systemd installed"
```

If any are missing:
```bash
sudo apt install pulseaudio-utils ffmpeg python3 systemd
```

## Test 1: Manual Script Testing

Test the recorder manually before installing as a service.

```bash
# Run the recorder in foreground
python3 teams_auto_recorder.py
```

**Expected output:**
```
Teams Auto-Recorder started. Monitoring for Teams audio...
Output directory: /var/log/teams-audio
Grace period: 30s
```

**Test steps:**
1. Start the recorder
2. Join a Teams meeting or play audio in Teams
3. Wait 2-5 seconds
4. Should see: `[HH:MM:SS] Started recording: /var/log/teams-audio/meeting_YYYY-MM-DD_HH-MM-SS.wav`
5. Leave the meeting
6. Wait 30 seconds
7. Should see: `[HH:MM:SS] Stopped recording: meeting_YYYY-MM-DD_HH-MM-SS`
8. Press Ctrl+C to stop the recorder

**Verify recording:**
```bash
ls -lh /var/log/teams-audio/
ffplay /var/log/teams-audio/meeting_*.wav  # Play the recording
ffprobe /var/log/teams-audio/meeting_*.wav  # Check properties
```

## Test 2: Teams Audio Detection

Verify that Teams audio is detectable by PulseAudio.

```bash
# With Teams running audio, check for Teams in pactl output
pactl list source-outputs | grep -i teams

# Or check for Microsoft
pactl list source-outputs | grep -i microsoft
```

**Expected:** Should see application names containing "teams" or "microsoft".

**If not detected:**
- Ensure Teams is actually playing audio (unmute mic, join meeting)
- Try Teams desktop app instead of web version
- Check: `pactl list source-outputs` for the full output

## Test 3: Recording Quality

Check that recordings have correct properties.

```bash
ffprobe /var/log/teams-audio/meeting_*.wav
```

**Expected output:**
```
Stream #0:0: Audio: pcm_s16le, 16000 Hz, mono, s16, 256 kb/s
```

**Verify:**
- Sample rate: 16000 Hz
- Channels: 1 (mono)
- Format: WAV

## Test 4: Systemd Service Installation

Install and test as a systemd service.

```bash
# Install
./install-recorder.sh

# Check service is enabled
systemctl is-enabled teams-auto-recorder
# Expected: enabled

# Check service is running
sudo systemctl status teams-auto-recorder
# Expected: active (running)

# View real-time logs
journalctl -u teams-auto-recorder -f
```

**Test meeting recording:**
1. Join Teams meeting
2. Watch logs: `journalctl -u teams-auto-recorder -f`
3. Should see: "Started recording"
4. Leave meeting
5. Wait 30 seconds
6. Should see: "Stopped recording"

## Test 5: Service Restart After Reboot

Test that service starts automatically on boot.

```bash
# Enable service
sudo systemctl enable teams-auto-recorder

# Reboot
sudo reboot

# After reboot, check service is running
sudo systemctl status teams-auto-recorder
```

## Test 6: Grace Period Handling

Verify that brief audio gaps don't stop recording.

**Test scenario:**
1. Join Teams meeting (recording starts)
2. Mute microphone for 10 seconds (audio gaps)
3. Unmute (audio resumes)
4. Recording should continue without stopping

**Verify:** Only one recording file created for the entire meeting.

## Test 7: Post-Processing

Test transcript generation from recordings.

```bash
# Ensure MCP server is set up
ls mcp-server-whisper/

# Process recordings
python3 process_recordings.py

# Check transcripts
ls -lh /var/log/teams-audio/*.txt
cat /var/log/teams-audio/meeting_*.txt
```

**Expected:**
- `.txt` file created for each `.wav` file
- Transcript contains meeting audio as text

## Test 8: Concurrent Meetings

Test behavior with multiple Teams instances.

**Not recommended:** The current implementation captures the first detected Teams audio stream. Running multiple Teams meetings simultaneously may result in mixed audio.

**Future enhancement:** Track by process PID to handle multiple meetings.

## Test 9: Error Handling

Test that errors are handled gracefully.

### No Teams Audio
```bash
# Run recorder with no Teams running
python3 teams_auto_recorder.py
```
**Expected:** Runs without errors, waits for Teams audio.

### No ffmpeg
```bash
# Temporarily rename ffmpeg to test error
sudo mv /usr/bin/ffmpeg /usr/bin/ffmpeg.bak
python3 teams_auto_recorder.py
# Start Teams meeting
```
**Expected:** Error message: "Error: ffmpeg not found"

```bash
# Restore ffmpeg
sudo mv /usr/bin/ffmpeg.bak /usr/bin/ffmpeg
```

### No PulseAudio
```bash
# Temporarily rename pactl
sudo mv /usr/bin/pactl /usr/bin/pactl.bak
python3 teams_auto_recorder.py
```
**Expected:** Error message: "Error: pactl not found"

```bash
# Restore pactl
sudo mv /usr/bin/pactl.bak /usr/bin/pactl
```

## Troubleshooting

### Recording Not Starting

**Check:** Is Teams audio actually detected?
```bash
pactl list source-outputs | grep -i "teams\|microsoft"
```

**If not found:**
- Ensure Teams is playing audio (join meeting, unmute)
- Try desktop app instead of web version
- Check full output: `pactl list source-outputs`

### Service Not Starting

**Check logs:**
```bash
journalctl -u teams-auto-recorder -n 50
```

**Common issues:**
- Wrong Python path: Check `ExecStart` in service file
- Permission issues: Ensure `/var/log/teams-audio/` owned by user
- PulseAudio not running: Check `XDG_RUNTIME_DIR` environment

### Recording File Empty

**Check:**
1. Is audio actually playing to default sink?
2. Try: `ffmpeg -f pulse -i default.monitor -t 5 test.wav`
3. Play test.wav to verify audio capture works

### High CPU Usage

**Expected:** ffmpeg uses ~2-5% CPU during recording. If higher:
- Check for multiple ffmpeg processes: `ps aux | grep ffmpeg`
- Verify recording is stopping properly after meetings

## Performance Benchmarks

**Expected resource usage:**

| Metric | Value |
|--------|-------|
| Memory (idle) | ~10 MB |
| Memory (recording) | ~20 MB |
| CPU (idle) | <1% |
| CPU (recording) | 2-5% |
| Disk (30 min meeting) | ~30 MB |

## Success Criteria

All tests should pass:

- [x] Manual script runs without errors
- [x] Teams audio is detected via pactl
- [x] Recording starts within 2 seconds of meeting start
- [x] Recording stops 30 seconds after meeting ends
- [x] Audio quality is 16kHz mono WAV
- [x] Systemd service installs and runs
- [x] Service survives reboot
- [x] Grace period handles brief audio gaps
- [x] Post-processing generates transcripts
- [x] Errors are handled gracefully

## Reporting Issues

If tests fail, please include:
1. Test number and description
2. Expected vs actual behavior
3. Relevant logs: `journalctl -u teams-auto-recorder -n 50`
4. System info: `uname -a`, `pulseaudio --version`, `ffmpeg -version`
5. PulseAudio output: `pactl list source-outputs`
