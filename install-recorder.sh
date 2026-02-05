#!/bin/bash
#
# Installation script for Teams Auto-Recorder
# See: docs/adr/0001-simplify-teams-audio-capture.md
#

set -e

echo "Installing Teams Auto-Recorder..."
echo

# Check for required commands
for cmd in pactl ffmpeg python3 systemctl; do
    if ! command -v $cmd &> /dev/null; then
        echo "Error: $cmd is not installed"
        echo "Please install: sudo apt install pulseaudio-utils ffmpeg python3 systemd"
        exit 1
    fi
done

# Create output directory
echo "Creating output directory..."
sudo mkdir -p /var/log/teams-audio
sudo chown $USER:$USER /var/log/teams-audio
echo "✓ Output directory: /var/log/teams-audio"

# Install systemd service
echo
echo "Installing systemd service..."
sudo cp teams-auto-recorder.service /etc/systemd/system/
sudo systemctl daemon-reload
echo "✓ Service installed"

# Enable and start service
echo
read -p "Do you want to enable and start the service now? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo systemctl enable teams-auto-recorder
    sudo systemctl start teams-auto-recorder
    echo "✓ Service enabled and started"
    echo
    echo "Check status with:"
    echo "  sudo systemctl status teams-auto-recorder"
    echo "  journalctl -u teams-auto-recorder -f"
else
    echo "Skipped. Enable later with:"
    echo "  sudo systemctl enable --now teams-auto-recorder"
fi

echo
echo "Installation complete!"
echo
echo "The recorder will automatically:"
echo "  1. Detect Teams meetings via audio streams"
echo "  2. Record to /var/log/teams-audio/meeting_YYYY-MM-DD_HH-MM-SS.wav"
echo "  3. Stop 30 seconds after meeting ends"
echo
echo "Manual testing:"
echo "  python3 teams_auto_recorder.py"
echo
echo "View recordings:"
echo "  ls -lh /var/log/teams-audio/"
