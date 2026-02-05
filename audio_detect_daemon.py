#!/usr/bin/env python3
"""Audio Stream Detection Daemon.

Monitors for audio streams (Teams, YouTube, custom patterns) and sends
desktop notifications with ready-to-use ffmpeg capture commands.
"""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from audio_detect.core import list_audio_streams, AudioStream


class AudioStreamDetector:
    """Background daemon that monitors audio streams and sends notifications."""

    def __init__(self, config_file: Optional[Path] = None):
        """Initialize the detector.
        
        Args:
            config_file: Path to configuration file
        """
        self.config_file = config_file or Path.home() / ".config" / "audio-detect" / "config.yaml"
        self.config = self.load_config()
        
        # State tracking
        self.notified_streams = set()  # Avoid duplicate notifications
        self.last_detection = {}  # Track last detection time per stream
        
        # Ensure directories exist
        self.setup_directories()
        
    def setup_directories(self):
        """Create necessary directories."""
        dirs = [
            self.config["paths"]["config_dir"],
            self.config["paths"]["log_dir"],
            self.config["paths"]["download_dir"],
        ]
        for dir_path in dirs:
            Path(dir_path).expanduser().mkdir(parents=True, exist_ok=True)
            
    def load_config(self) -> Dict:
        """Load configuration from file."""
        default_config = {
            "detection": {
                "poll_interval": 2,
                "cooldown": 30,
            },
            "targets": {
                "teams": {
                    "enabled": True,
                    "patterns": [
                        "microsoft teams",
                        "teams.microsoft.com",
                        "teams meeting",
                        "microsoft teams meeting"
                    ]
                },
                "youtube": {
                    "enabled": True,
                    "patterns": [
                        "youtube",
                        "youtu.be"
                    ]
                },
                "custom": {
                    "enabled": False,
                    "patterns": []
                }
            },
            "paths": {
                "download_dir": "~/AudioCaptures",
                "config_dir": "~/.config/audio-detect",
                "log_dir": "~/.local/share/audio-detect",
            },
            "organization": {
                "create_subdirs": True,
                "filename_template": "{type}_{timestamp}.wav"
            },
            "notification": {
                "method": "desktop",
                "auto_copy": True,
                "timeout": 10,
                "title": "🎤 Audio Stream Detected"
            }
        }
        
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    user_config = yaml.safe_load(f)
                # Merge with defaults
                return self.merge_configs(default_config, user_config)
            except Exception as e:
                print(f"Warning: Could not load config file {self.config_file}: {e}")
                print("Using default configuration.")
        
        # Create default config file
        self.save_config(default_config)
        return default_config
    
    def merge_configs(self, default: Dict, user: Dict) -> Dict:
        """Recursively merge user config with defaults."""
        result = default.copy()
        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self.merge_configs(result[key], value)
            else:
                result[key] = value
        return result
    
    def save_config(self, config: Dict):
        """Save configuration to file."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, indent=2)
    
    def get_patterns(self) -> List[str]:
        """Get all enabled patterns."""
        patterns = []
        
        if self.config["targets"]["teams"]["enabled"]:
            patterns.extend(self.config["targets"]["teams"]["patterns"])
            
        if self.config["targets"]["youtube"]["enabled"]:
            patterns.extend(self.config["targets"]["youtube"]["patterns"])
            
        if self.config["targets"]["custom"]["enabled"]:
            patterns.extend(self.config["targets"]["custom"]["patterns"])
            
        return patterns
    
    def classify_stream(self, stream: AudioStream) -> Optional[str]:
        """Classify stream type based on patterns."""
        app_lower = stream.application.lower()
        media_lower = stream.media.lower()
        
        # Check Teams patterns
        if self.config["targets"]["teams"]["enabled"]:
            for pattern in self.config["targets"]["teams"]["patterns"]:
                if pattern.lower() in app_lower or pattern.lower() in media_lower:
                    return "teams"
        
        # Check YouTube patterns
        if self.config["targets"]["youtube"]["enabled"]:
            for pattern in self.config["targets"]["youtube"]["patterns"]:
                if pattern.lower() in app_lower or pattern.lower() in media_lower:
                    return "youtube"
        
        # Check custom patterns
        if self.config["targets"]["custom"]["enabled"]:
            for pattern in self.config["targets"]["custom"]["patterns"]:
                if pattern.lower() in app_lower or pattern.lower() in media_lower:
                    return "custom"
        
        return None
    
    def generate_ffmpeg_command(self, stream: AudioStream, stream_type: str) -> str:
        """Generate ffmpeg command for capturing the stream."""
        download_dir = Path(self.config["paths"]["download_dir"]).expanduser()
        
        # Create subdirectory if enabled
        if self.config["organization"]["create_subdirs"]:
            output_dir = download_dir / stream_type
        else:
            output_dir = download_dir
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.config["organization"]["filename_template"].format(
            type=stream_type,
            timestamp=timestamp
        )
        output_file = output_dir / filename
        
        return f"ffmpeg -f pulse -i {stream.monitor} -ac 1 -ar 16000 {output_file}"
    
    def send_notification(self, stream: AudioStream, stream_type: str, ffmpeg_cmd: str):
        """Send desktop notification with ffmpeg command."""
        title = self.config["notification"]["title"]
        
        # Build notification body
        body = f"{stream.application} - {stream.media}\n\n{ffmpeg_cmd}"
        
        # Try desktop notification first
        try:
            cmd = [
                "notify-send",
                "-t", str(self.config["notification"]["timeout"] * 1000),
                "-i", "audio-x-generic",
                title,
                body
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            
            # Copy to clipboard if enabled
            if self.config["notification"]["auto_copy"]:
                try:
                    import pyperclip
                    pyperclip.copy(ffmpeg_cmd)
                    print(f"Copied to clipboard: {ffmpeg_cmd}")
                except ImportError:
                    print("pyperclip not available - install with: pip install pyperclip")
                except Exception as e:
                    print(f"Could not copy to clipboard: {e}")
                    
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback to xmessage
            try:
                cmd = [
                    "xmessage",
                    "-timeout", str(self.config["notification"]["timeout"]),
                    "-buttons", "Copy Command:1,Dismiss:0",
                    title,
                    body
                ]
                result = subprocess.run(cmd, capture_output=True)
                
                # If user clicked "Copy Command"
                if result.returncode == 1:
                    try:
                        import pyperclip
                        pyperclip.copy(ffmpeg_cmd)
                        print(f"Copied to clipboard: {ffmpeg_cmd}")
                    except ImportError:
                        print(f"Command to copy: {ffmpeg_cmd}")
                        
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Last resort - print to console
                print(f"\n{'='*60}")
                print(f"{title}")
                print(f"{'='*60}")
                print(f"{stream.application} - {stream.media}")
                print(f"\n{ffmpeg_cmd}")
                print(f"{'='*60}\n")
    
    def should_notify(self, stream: AudioStream, stream_type: str) -> bool:
        """Check if we should send notification for this stream."""
        stream_key = f"{stream.id}:{stream_type}"
        current_time = time.time()
        
        # Check if we've notified this stream recently
        if stream_key in self.last_detection:
            time_since_last = current_time - self.last_detection[stream_key]
            if time_since_last < self.config["detection"]["cooldown"]:
                return False
        
        return True
    
    def detect_and_notify(self):
        """Detect streams and send notifications."""
        try:
            streams = list_audio_streams()
            
            for stream in streams:
                if not stream.is_running:
                    continue
                
                stream_type = self.classify_stream(stream)
                if not stream_type:
                    continue
                
                if self.should_notify(stream, stream_type):
                    ffmpeg_cmd = self.generate_ffmpeg_command(stream, stream_type)
                    self.send_notification(stream, stream_type, ffmpeg_cmd)
                    
                    # Update tracking
                    stream_key = f"{stream.id}:{stream_type}"
                    self.notified_streams.add(stream_key)
                    self.last_detection[stream_key] = time.time()
                    
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Notified: {stream.application} - {stream.media}")
                    
        except Exception as e:
            print(f"Error in detection loop: {e}")
    
    def run_forever(self):
        """Main detection loop."""
        print(f"Audio Stream Detection Daemon started")
        print(f"Config file: {self.config_file}")
        print(f"Monitoring patterns: {', '.join(self.get_patterns())}")
        print(f"Poll interval: {self.config['detection']['poll_interval']}s")
        print(f"Press Ctrl+C to stop\n")
        
        try:
            while True:
                self.detect_and_notify()
                time.sleep(self.config["detection"]["poll_interval"])
        except KeyboardInterrupt:
            print("\nStopping daemon...")
        except Exception as e:
            print(f"Fatal error: {e}")
            sys.exit(1)


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    print("\nReceived shutdown signal, stopping daemon...")
    sys.exit(0)


def main():
    """Main entry point."""
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description="Audio Stream Detection Daemon")
    parser.add_argument("--config", type=Path, help="Configuration file path")
    parser.add_argument("--dry-run", action="store_true", help="Run once and exit")
    args = parser.parse_args()
    
    print(f"Audio Stream Detection Daemon starting...")
    print(f"Config file: {args.config or 'default'}")
    print(f"Dry run: {args.dry_run}")
    
    # Create and run detector
    try:
        detector = AudioStreamDetector(args.config)
        print(f"Detector initialized successfully")
        
        if args.dry_run:
            print("Dry run - detecting streams once...")
            detector.detect_and_notify()
        else:
            print("Starting detection loop...")
            detector.run_forever()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
