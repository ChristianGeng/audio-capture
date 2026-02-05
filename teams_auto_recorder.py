#!/usr/bin/env python3
"""Automatic Teams Meeting Audio Recorder.

Detects Microsoft Teams meetings via PulseAudio and automatically records audio
with zero user intervention. Designed to run as a systemd service.

Architecture Decision: See docs/adr/0001-simplify-teams-audio-capture.md
"""

import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


class TeamsRecorder:
    """Automatic audio recorder for Microsoft Teams meetings."""

    def __init__(
        self,
        output_dir: Path = Path("/var/log/teams-audio"),
        grace_period: int = 30,
        poll_interval: int = 2
    ):
        """Initialize the recorder.

        Args:
            output_dir: Directory to save recordings
            grace_period: Seconds to wait after Teams audio disappears before stopping
            poll_interval: Seconds between audio stream checks
        """
        self.output_dir = output_dir
        self.grace_period = grace_period
        self.poll_interval = poll_interval

        # State
        self.recording_process = None
        self.is_recording = False
        self.last_teams_seen = None
        self.current_meeting_id = None

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def detect_teams_audio(self) -> bool:
        """Check if Teams audio stream exists in PulseAudio.

        Returns:
            True if Teams audio detected, False otherwise
        """
        try:
            result = subprocess.run(
                ['pactl', 'list', 'source-outputs'],
                capture_output=True,
                text=True,
                timeout=5
            )

            # Look for Teams in application name or binary
            output_lower = result.stdout.lower()
            return 'teams' in output_lower or 'microsoft' in output_lower

        except subprocess.TimeoutExpired:
            print("Warning: pactl command timed out", file=sys.stderr)
            return False
        except FileNotFoundError:
            print("Error: pactl not found. Is PulseAudio installed?", file=sys.stderr)
            sys.exit(1)

    def start_recording(self):
        """Start ffmpeg recording of Teams audio."""
        # Generate meeting ID
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.current_meeting_id = f"meeting_{timestamp}"

        # Output file path
        output_file = self.output_dir / f"{self.current_meeting_id}.wav"

        # Write current meeting ID for Chrome extension coordination
        meeting_marker = self.output_dir / "current_meeting.txt"
        try:
            with open(meeting_marker, 'w') as f:
                f.write(self.current_meeting_id)
        except IOError as e:
            print(f"Warning: Could not write meeting marker: {e}", file=sys.stderr)

        # Start ffmpeg recording
        try:
            self.recording_process = subprocess.Popen(
                [
                    'ffmpeg',
                    '-f', 'pulse',
                    '-i', 'default.monitor',  # Capture from default sink monitor
                    '-ac', '1',               # Mono audio
                    '-ar', '16000',           # 16kHz sample rate
                    '-y',                     # Overwrite if exists
                    str(output_file)
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            self.is_recording = True
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Started recording: {output_file}")

        except FileNotFoundError:
            print("Error: ffmpeg not found. Please install ffmpeg.", file=sys.stderr)
            sys.exit(1)

    def stop_recording(self):
        """Stop ffmpeg recording."""
        if self.recording_process:
            try:
                self.recording_process.terminate()
                self.recording_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.recording_process.kill()
                self.recording_process.wait()
            finally:
                self.recording_process = None

        self.is_recording = False

        if self.current_meeting_id:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Stopped recording: {self.current_meeting_id}")
            self.current_meeting_id = None

        # Remove meeting marker
        meeting_marker = self.output_dir / "current_meeting.txt"
        meeting_marker.unlink(missing_ok=True)

    def run(self):
        """Main monitoring loop."""
        print(f"Teams Auto-Recorder started. Monitoring for Teams audio...")
        print(f"Output directory: {self.output_dir}")
        print(f"Grace period: {self.grace_period}s")

        while True:
            try:
                teams_active = self.detect_teams_audio()
                current_time = time.time()

                if teams_active:
                    self.last_teams_seen = current_time
                    if not self.is_recording:
                        self.start_recording()
                else:
                    # Teams audio not detected
                    if self.is_recording and self.last_teams_seen:
                        # Check grace period
                        elapsed = current_time - self.last_teams_seen
                        if elapsed > self.grace_period:
                            self.stop_recording()

                time.sleep(self.poll_interval)

            except KeyboardInterrupt:
                print("\nShutting down...")
                self.stop_recording()
                break
            except Exception as e:
                print(f"Error in main loop: {e}", file=sys.stderr)
                time.sleep(self.poll_interval)


def main():
    """Entry point for the recorder."""
    recorder = TeamsRecorder()

    # Set up signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        print(f"\nReceived signal {signum}, shutting down...")
        recorder.stop_recording()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the recorder
    recorder.run()


if __name__ == "__main__":
    main()
