#!/usr/bin/env python3
"""Demo script showing how to use the audio stream transcriber."""

import subprocess
import time
from pathlib import Path

def show_audio_devices():
    """Show available audio devices."""
    print("=== Available Audio Devices ===")
    print("Run this command to find your audio device:")
    print("wpctl status")
    print()
    print("Look for:")
    print("1. The default sink (marked with *) under 'Sinks'")
    print("2. The corresponding device name under 'Default Configured Node Names'")
    print()

def show_ffmpeg_command():
    """Show the ffmpeg command for audio capture."""
    print("=== FFmpeg Audio Capture Command ===")
    device = "alsa_output.usb-Razer_Razer_Kraken_V3_X_000000000001-00.analog-stereo.monitor"
    
    ffmpeg_cmd = f"""ffmpeg -f pulse -i {device} -ac 1 -ar 16000 -f f32le -"""
    
    print("Basic ffmpeg command to capture audio:")
    print(ffmpeg_cmd)
    print()
    print("To save to file instead:")
    print(f"ffmpeg -f pulse -i {device} -ac 1 -ar 16000 test_audio.wav")
    print()

def test_ffmpeg_capture():
    """Test ffmpeg audio capture for 5 seconds."""
    print("=== Testing FFmpeg Audio Capture ===")
    print("This will capture 5 seconds of audio to test_capture.wav")
    print("Start playing some audio now!")
    print()
    
    device = "alsa_output.usb-Razer_Razer_Kraken_V3_X_000000000001-00.analog-stereo.monitor"
    
    cmd = [
        "ffmpeg",
        "-f", "pulse",
        "-i", device,
        "-ac", "1",
        "-ar", "16000",
        "-t", "5",  # 5 seconds
        "-y",  # Overwrite output file
        "test_capture.wav"
    ]
    
    print(f"Running: {' '.join(cmd)}")
    print("Recording for 5 seconds...")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ Audio capture successful!")
            print(f"File saved as: test_capture.wav ({Path('test_capture.wav').stat().st_size} bytes)")
        else:
            print("❌ Audio capture failed:")
            print(result.stderr)
    except subprocess.TimeoutExpired:
        print("❌ Audio capture timed out")
    except FileNotFoundError:
        print("❌ ffmpeg not found. Install with: sudo apt install ffmpeg")

def show_usage():
    """Show how to use the transcriber."""
    print("=== Using the Real-time Transcriber ===")
    print()
    print("1. Set up your OpenAI API key in .env:")
    print("   OPENAI_API_KEY=your_actual_key_here")
    print()
    print("2. Start the transcriber:")
    print("   audio-stream start")
    print()
    print("3. Or with custom settings:")
    print("   audio-stream start --chunk-duration 3 --overlap 0.5")
    print()
    print("4. Press Ctrl+C to stop")
    print()

def main():
    """Run the demo."""
    print("🎤 Audio Stream Transcriber Demo")
    print("=" * 50)
    print()
    
    show_audio_devices()
    show_ffmpeg_command()
    
    print("Would you like to test ffmpeg audio capture? (y/n): ", end="")
    try:
        choice = input().lower().strip()
        if choice == 'y':
            test_ffmpeg_capture()
            print()
    except KeyboardInterrupt:
        print("\nDemo cancelled.")
        return
    
    show_usage()
    
    print("📚 For more information, see README.md")
    print("🔧 Need help? Check the troubleshooting section in README.md")

if __name__ == "__main__":
    main()
