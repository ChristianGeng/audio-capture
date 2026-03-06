# Audio Capture — Teams Meeting Recorder & Tracker

Record audio and track Microsoft Teams meeting metadata (participants,
speakers, join/leave events) from a single CLI command. Uses the Chrome
DevTools Protocol to poll the Teams web UI for real-time state.

## Prerequisites

- **Linux** with PulseAudio or PipeWire
- **Google Chrome** (or Chromium)
- **ffmpeg** on PATH
- **Python >= 3.10** with [uv](https://docs.astral.sh/uv/)

## Installation

```bash
git clone https://github.com/ChristianGeng/audio-capture.git
cd audio-capture
uv sync
```

## Development Setup

### 1. Start Chrome with the remote debugging port

Close all existing Chrome windows first, then:

```bash
google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
```

### 2. Verify the debug port is accessible

```bash
curl http://localhost:9222/json/version
```

You should see JSON with Chrome version info. If you get
"Connection refused", Chrome is not running with the debug port.

### 3. Open Teams in the debug Chrome

Navigate to <https://teams.microsoft.com> and join a meeting.

### 4. Confirm the Teams tab is visible

```bash
uv run audio-detect tabs
```

This lists all Chrome tabs and their audio state.

## CLI Commands

### `audio-detect list`

List active PulseAudio/PipeWire audio streams:

```bash
uv run audio-detect list            # compact table
uv run audio-detect list --wide     # full sink names
uv run audio-detect list --json     # JSON output
```

### `audio-detect tabs`

List Chrome tabs and their media playback state:

```bash
uv run audio-detect tabs
```

### `audio-detect track`

Track a live Teams meeting without audio recording.
Polls the Teams tab DOM and writes change events to JSONL:

```bash
uv run audio-detect track
uv run audio-detect track --interval 1.5 --output meeting.jsonl
```

Options:

- `--interval` — seconds between DOM polls (default: 1.5)
- `--snapshot-interval` — seconds between full-state snapshots (default: 120)
- `--speaker-debounce` — consecutive polls before confirming speaker (default: 3)
- `--output` / `-o` — JSONL output file

### `audio-detect record`

Record audio **and** track the meeting simultaneously.
Runs ffmpeg and the Teams tracker in parallel with a shared start timestamp:

```bash
uv run audio-detect record
uv run audio-detect record --set-volume --bit-depth 24
uv run audio-detect record --volume-boost 6 --sample-rate 24000
```

Options:

- `--bit-depth` — 16, 24, or 32 (default: 24)
- `--sample-rate` — Hz (default: 48000)
- `--volume-boost` — dB boost applied during capture (default: 0)
- `--set-volume` — auto-set PulseAudio sink to 100% before recording
- `--monitor` / `-m` — PulseAudio monitor source (auto-detected)
- `--output-dir` / `-o` — output directory (default: `meeting_<timestamp>/`)
- `--interval` — tracker poll interval (default: 1.5)
- `--snapshot-interval` — full snapshot interval (default: 120)

Output directory:

```
meeting_20260206_113500/
├── audio.wav          # raw audio capture (24-bit / 48kHz)
├── events.jsonl       # timestamped meeting events
└── meta.json          # shared metadata for alignment
```

### `audio-detect suggest`

Show ffmpeg recording commands for detected streams:

```bash
uv run audio-detect suggest
```

### `audio-detect status`

Show system status (tools, streams, virtual sinks):

```bash
uv run audio-detect status
```

## Output Formats

### events.jsonl

One JSON object per line. Event types:

| Type | Description |
|------|-------------|
| `join` | Participant appeared in the meeting |
| `leave` | Participant left the meeting |
| `speaker_start` | Participant started speaking (debounced) |
| `speaker_stop` | Participant stopped speaking |
| `mute` / `unmute` | Participant muted or unmuted |
| `screen_share_start` / `screen_share_stop` | Screen sharing toggled |
| `chat_message` | New chat message (text, links, files) |
| `file_shared` | File attachment shared in chat |
| `system_message` | System message (e.g. "Meeting started") |
| `snapshot` | Periodic full-state snapshot |

**Note**: Chat tracking requires the chat panel to be open in Teams
during the meeting. If closed, chat events are silently skipped.

Examples:

```json
{"ts": "2026-02-06T10:49:30+00:00", "type": "speaker_start", "email": "jwagner@audeering.com", "name": "Johannes Wagner"}
{"ts": "2026-02-06T11:01:36+00:00", "type": "chat_message", "message_ts": "2026-02-06T11:01:36.622Z", "author": "Dionyssos Kounadis-Bastian", "text": "Here is the file", "files": ["recording.wav"]}
{"ts": "2026-02-06T11:01:36+00:00", "type": "file_shared", "message_ts": "2026-02-06T11:01:36.622Z", "author": "Dionyssos Kounadis-Bastian", "filename": "recording.wav"}
```

### meta.json

Shared metadata for aligning events to the audio waveform:

```json
{
  "start_time": "2026-02-06T10:49:02+00:00",
  "end_time": "2026-02-06T10:57:30+00:00",
  "duration_seconds": 508.0,
  "monitor_source": "alsa_output.usb-...analog-stereo.monitor",
  "sample_rate": 48000,
  "channels": 1,
  "bit_depth": 24,
  "volume_boost_db": 0.0,
  "sink_volume_pct": 86
}
```

To align an event to the audio: `offset_seconds = event_ts - start_time`.

## Polling Frequency & Accuracy

The tracker polls the Teams DOM via Chrome DevTools Protocol.
Each poll takes approximately **6 ms** (WebSocket connect + JS injection +
response), so even very high poll rates have negligible CPU impact.

| Interval | Polls/sec | Duty cycle | Use case |
|----------|-----------|------------|----------|
| 0.125s | 8/sec | ~4.8% | Maximum resolution diarization |
| 0.25s | 4/sec | ~2.4% | High-resolution diarization |
| 0.5s | 2/sec | ~1.2% | Fine-grained speaker tracking |
| **1.5s** | **0.7/sec** | **~0.4%** | **Default — good balance** |
| 2.0s | 0.5/sec | ~0.3% | Low overhead |
| 5.0s | 0.2/sec | ~0.1% | Minimal — join/leave only |

Examples:

```bash
# 8 polls/sec — best possible speaker timing (~125ms resolution)
uv run audio-detect record --interval 0.125 --speaker-debounce 8

# 4 polls/sec — high resolution (~250ms)
uv run audio-detect record --interval 0.25 --speaker-debounce 6

# Default — 1.5s interval, good for most meetings
uv run audio-detect record
```

When using fast polling, increase `--speaker-debounce` proportionally
to keep the debounce window roughly the same (~3-4 seconds):

| Interval | Recommended debounce | Debounce window |
|----------|---------------------|-----------------|
| 0.125s | 24–32 | 3–4s |
| 0.25s | 12–16 | 3–4s |
| 0.5s | 6–8 | 3–4s |
| 1.0s | 3–4 | 3–4s |
| **1.5s** | **3** | **4.5s** |

| Setting | Default | Effect |
|---------|---------|--------|
| `--interval` | 1.5s | DOM poll frequency. Lower = finer resolution. |
| `--speaker-debounce` | 3 polls | Consecutive polls before confirming speaker. |
| `--snapshot-interval` | 120s | Full participant state dump. |

**Timestamp accuracy**: Event timestamps use `datetime.now(UTC)` and are
accurate to the poll interval. At 8 polls/sec, speaker transitions are
captured within ~125 ms. The audio file starts at the exact `start_time`
in `meta.json`.

**Recommended defaults**: 1.5s interval with 3-poll debounce gives a good
balance between responsiveness and noise filtering. For detailed diarization,
use `--interval 0.25 --speaker-debounce 12`.

## Audio Quality

| Bit depth | Dynamic range | Use case |
|-----------|---------------|----------|
| 16-bit | 96 dB | Small files, speech-only |
| **24-bit** | **144 dB** | **Default — no clipping risk** |
| 32-bit | 192 dB | Archival |

24-bit at 48kHz is the default. This gives 144 dB of dynamic range,
which makes clipping from quantization virtually impossible for meeting
audio. The only clipping risk is if `--volume-boost` is set too high on
already-loud audio.

## Architecture

```
audio_detect/
├── cli.py            # Click CLI commands
├── core.py           # PulseAudio stream detection
├── detectors.py      # Audio state detectors (PulseAudio, Browser)
├── recorder.py       # Unified recorder (ffmpeg + tracker)
└── teams_tracker.py  # Teams DOM polling via Chrome DevTools Protocol
```

The tracker injects JavaScript into the Teams tab via WebSocket to read:

- `data-is-speaking="true"` on voice level overlays
- `aria-label` on participant tiles (name, muted, video state)
- `data-tid` attributes for participant emails
- `data-tid="call-duration"` for meeting duration
