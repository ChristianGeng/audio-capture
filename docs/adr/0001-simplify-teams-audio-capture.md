# ADR-0001: Simplify Teams Audio Capture: From Chrome Tab Isolation to Direct Audio Stream Detection

## Status

Accepted

## Date

2024-02-04

## Context

The current `chrome_tab_diarizer.py` implementation (415 lines) was designed for manual Chrome tab audio capture with speaker diarization. It requires:
- Manual PulseAudio virtual sink creation
- Manual audio routing via pavucontrol GUI
- User to type in tab name
- Real-time processing with heavy ML models (pyannote.audio, torch)

**User's Actual Requirement**: Automatically record Microsoft Teams meetings with zero user intervention. Audio files can be processed later; real-time transcription is not needed.

**Key Insight**: The current architecture is over-engineered for the actual use case. Teams is a standalone application (not a Chrome tab), and we don't need immediate transcription or diarization.

## Decision Drivers

* **Zero manual intervention** - System must detect and record automatically
* **Immediate value** - Need working solution quickly (2-4 hours)
* **Simplicity** - Minimize code complexity and dependencies
* **Future extensibility** - Support adding Chrome DOM metadata extraction later
* **Ubuntu service deployment** - Must run as systemd background service

## Considered Options

### Option 1: Simplify to Audio-Only Daemon (SELECTED)
Build a minimal Python daemon (~100 lines) that:
- Detects Teams audio via `pactl list source-outputs`
- Auto-routes to virtual sink using `pactl move-source-output`
- Starts/stops ffmpeg recording automatically
- Saves timestamped WAV files
- Runs as systemd service

**Pros**:
- 75% less code (100 vs 415 lines)
- No manual steps (fully automated)
- No heavy dependencies (subprocess only)
- Fast implementation (2-4 hours)
- Works with Teams desktop app directly

**Cons**:
- No meeting metadata (title, participants) initially
- Requires future Chrome extension for metadata

### Option 2: Keep Current Chrome Tab Architecture
Continue with manual pavucontrol routing and Chrome tab isolation.

**Pros**:
- Already implemented
- Speaker diarization included

**Cons**:
- Requires manual routing (deal-breaker for automation)
- 415 lines of complexity
- Doesn't match Teams use case (not a Chrome tab)
- Heavy ML dependencies

### Option 3: Chrome Extension First
Build Chrome extension to detect Teams web meetings and extract metadata.

**Pros**:
- Access to meeting metadata (title, participants, chat)
- Works for Teams web version

**Cons**:
- Requires extension development (5-7 hours)
- User must use Teams in browser (not desktop app)
- No immediate audio recording solution

## Decision

We will implement **Option 1**: Build a simple audio recording daemon with extensibility for future metadata extraction.

## Architecture

### Separation of Concerns

Two independent components coordinated via filesystem:

1. **Audio Recording Daemon** (implement now - Phase 1)
   - Detects Teams audio streams: `pactl list source-outputs`
   - Auto-routes to virtual sink: `pactl move-source-output`
   - Records with ffmpeg: `ffmpeg -f pulse -i teams_recorder.monitor`
   - Saves: `/var/log/teams-audio/meeting_YYYY-MM-DD_HH-MM-SS.wav`
   - Complexity: ~100 lines Python

2. **Chrome Extension** (implement later - Phase 2)
   - Scrapes Teams web DOM (meeting title, participants, chat)
   - Writes metadata: `/var/log/teams-audio/meeting_YYYY-MM-DD_HH-MM-SS.json`
   - Uses native messaging to access filesystem
   - Complexity: ~150 lines JavaScript + ~80 lines Python bridge

### Coordination

Both components use **shared meeting ID** (timestamp-based):
- Meeting ID: `meeting_2024-01-15_10-30`
- Audio file: `meeting_2024-01-15_10-30.wav`
- Metadata file: `meeting_2024-01-15_10-30.json`
- Correlation: Match by filename prefix

### Data Flow

```
Teams Meeting Starts
    ↓
Daemon detects Teams audio (pactl)
    ↓
Auto-route to virtual sink (pactl move-source-output)
    ↓
Start ffmpeg recording
    ↓
Write current_meeting.txt (for Chrome extension to read)
    ↓
Meeting ends (30s grace period)
    ↓
Stop recording
    ↓
[Later] Chrome extension writes matching .json file
    ↓
[Later] Post-processing merges audio + metadata
```

## Consequences

### Positive

- **Immediate value**: Working audio recording in 2-4 hours vs weeks
- **Zero intervention**: Fully automated, no manual routing
- **Simplicity**: 75% less code (100 vs 415 lines)
- **Lower dependencies**: No torch, pyannote, or heavy ML libraries for Phase 1
- **Better fit**: Works with Teams desktop app (not just browser)
- **Extensible**: Chrome DOM access can be added later without modifying audio code
- **Debuggable**: Each component is small and testable independently
- **Systemd-friendly**: Simple daemon design for service deployment

### Negative

- **No initial metadata**: Meeting title, participants not captured until Phase 2
- **Two-phase implementation**: Need Chrome extension later for full functionality
- **PulseAudio dependency**: Tied to PulseAudio (not Pipewire or ALSA)
- **Teams naming assumption**: Detection relies on Teams using "teams" or "microsoft" in PulseAudio stream names

### Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Teams changes PulseAudio stream naming | Detection fails | Add regex patterns, monitor for Teams updates, fallback to manual override |
| Chrome extension complexity | Delayed Phase 2 | Audio recording provides immediate value; metadata is enhancement |
| Multiple Teams instances | Wrong audio captured | Track by process PID, validate single active meeting |
| Virtual sink conflicts | Recording fails | Check sink exists, create if needed, idempotent setup |

## Implementation Notes

### Phase 1: Audio Recording (Now)

**Files to create**:
- `teams_auto_recorder.py` (~100 lines)
- `/etc/systemd/system/teams-auto-recorder.service`
- `/etc/pulse/default.pa` (virtual sink config)

**Key functions**:
```python
def detect_teams_audio() -> bool:
    # Check pactl list source-outputs for teams

def start_recording():
    # Create meeting ID, route audio, start ffmpeg

def stop_recording():
    # Terminate ffmpeg, cleanup
```

**Dependencies**: Python stdlib only (subprocess, time, signal)

### Phase 2: Chrome DOM Access (Later)

**Files to create**:
- `chrome-extension/manifest.json`
- `chrome-extension/content.js` (DOM scraper)
- `chrome-extension/background.js` (native messaging)
- `native-host.py` (filesystem bridge)

**Integration**: Reads `current_meeting.txt` to get meeting ID, writes matching `.json` file.

## Validation

### Success Criteria (Phase 1)
- [ ] No manual intervention required
- [ ] Recording starts within 2 seconds of Teams audio detection
- [ ] Recording stops 30 seconds after meeting ends
- [ ] Service survives system reboots
- [ ] Audio files are playable and contain meeting audio
- [ ] <100 lines of core code

### Success Criteria (Phase 2)
- [ ] Chrome extension extracts meeting metadata
- [ ] JSON files match audio file naming
- [ ] Post-processing correlates audio + metadata

## Related Decisions

- Future ADR: Chrome extension implementation strategy
- Future ADR: Post-processing pipeline architecture
- Future ADR: Storage and retention policies

## References

- [PulseAudio pactl Documentation](https://www.freedesktop.org/wiki/Software/PulseAudio/Documentation/User/PulseAudioStoleMySound/)
- [Chrome Native Messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging)
- [FFmpeg PulseAudio Capture](https://trac.ffmpeg.org/wiki/Capture/PulseAudio)
- Plan file: `/home/cgeng/.claude/plans/ethereal-drifting-hartmanis.md`
