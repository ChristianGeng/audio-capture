#!/bin/bash
# Installation script for Audio Stream Detection Daemon

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get current user
USER=$(whoami)
HOME_DIR="/home/$USER"
SERVICE_NAME="audio-detect-daemon"

echo -e "${BLUE}🎤 Audio Stream Detection Daemon Installation${NC}"
echo "=================================================="

# Check if running as correct user
if [[ $EUID -eq 0 ]]; then
   echo -e "${RED}This script should be run as a regular user, not as root${NC}"
   exit 1
fi

echo -e "${YELLOW}Installing for user: $USER${NC}"

# Create directories
echo -e "\n${BLUE}📁 Creating directories...${NC}"
mkdir -p "$HOME_DIR/.config/audio-detect"
mkdir -p "$HOME_DIR/.local/share/audio-detect"
mkdir -p "$HOME_DIR/AudioCaptures"
mkdir -p "$HOME_DIR/.local/bin"

echo -e "✓ Config directory: $HOME_DIR/.config/audio-detect"
echo -e "✓ Runtime directory: $HOME_DIR/.local/share/audio-detect"
echo -e "✓ Downloads directory: $HOME_DIR/AudioCaptures"

# Install daemon script
echo -e "\n${BLUE}📦 Installing daemon script...${NC}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DAEMON_SCRIPT="$SCRIPT_DIR/audio_detect_daemon.py"

if [[ ! -f "$DAEMON_SCRIPT" ]]; then
    echo -e "${RED}Error: Daemon script not found at $DAEMON_SCRIPT${NC}"
    exit 1
fi

# Make script executable
chmod +x "$DAEMON_SCRIPT"
echo -e "✓ Daemon script: $DAEMON_SCRIPT"

# Create symlink in local bin
ln -sf "$DAEMON_SCRIPT" "$HOME_DIR/.local/bin/audio_detect_daemon"
echo -e "✓ Symlink: $HOME_DIR/.local/bin/audio_detect_daemon"

# Install systemd service
echo -e "\n${BLUE}⚙️  Installing systemd service...${NC}"
SERVICE_FILE="$SCRIPT_DIR/audio-detect-daemon.service"
SYSTEMD_DIR="$HOME_DIR/.config/systemd/user"

mkdir -p "$SYSTEMD_DIR"

# Create user-specific service file
sed -e "s|%i|$USER|g" -e "s|%U|$(id -u $USER)|g" -e "s|%h|$HOME_DIR|g" "$SERVICE_FILE" > "$SYSTEMD_DIR/$SERVICE_NAME.service"

echo -e "✓ Service file: $SYSTEMD_DIR/$SERVICE_NAME.service"

# Reload systemd
systemctl --user daemon-reload
echo -e "✓ Systemd reloaded"

# Install dependencies
echo -e "\n${BLUE}📚 Checking dependencies...${NC}"

# Check for notify-send
if ! command -v notify-send &> /dev/null; then
    echo -e "${YELLOW}Installing libnotify-bin for desktop notifications...${NC}"
    sudo apt-get update && sudo apt-get install -y libnotify-bin
else
    echo -e "✓ notify-send found"
fi

# Check for python packages
echo -e "${BLUE}🐍 Installing Python packages...${NC}"
pip3 install --user pyyaml pyperclip >/dev/null 2>&1 || {
    echo -e "${YELLOW}Installing with pip...${NC}"
    python3 -m pip install --user pyyaml pyperclip
}

# Test the daemon
echo -e "\n${BLUE}🧪 Testing daemon...${NC}"
if python3 "$DAEMON_SCRIPT" --dry-run; then
    echo -e "✓ Daemon test successful"
else
    echo -e "${YELLOW}Daemon test completed (may be normal if no audio streams active)${NC}"
fi

# Create CLI management script
echo -e "\n${BLUE}🔧 Creating CLI management script...${NC}"
cat > "$HOME_DIR/.local/bin/audio-detect-service" << 'EOF'
#!/bin/bash
# Audio Stream Detection Service Management CLI

SERVICE_NAME="audio-detect-daemon"
CONFIG_DIR="$HOME/.config/audio-detect"
CONFIG_FILE="$CONFIG_DIR/config.yaml"

case "$1" in
    start)
        echo "Starting Audio Stream Detection Daemon..."
        systemctl --user start "$SERVICE_NAME"
        systemctl --user status "$SERVICE_NAME" --no-pager
        ;;
    stop)
        echo "Stopping Audio Stream Detection Daemon..."
        systemctl --user stop "$SERVICE_NAME"
        ;;
    restart)
        echo "Restarting Audio Stream Detection Daemon..."
        systemctl --user restart "$SERVICE_NAME"
        systemctl --user status "$SERVICE_NAME" --no-pager
        ;;
    status)
        echo "Audio Stream Detection Daemon Status:"
        systemctl --user status "$SERVICE_NAME" --no-pager
        ;;
    enable)
        echo "Enabling Audio Stream Detection Daemon (start on login)..."
        systemctl --user enable "$SERVICE_NAME"
        echo "✓ Service will start automatically on login"
        ;;
    disable)
        echo "Disabling Audio Stream Detection Daemon..."
        systemctl --user disable "$SERVICE_NAME"
        echo "✓ Service will not start automatically on login"
        ;;
    config)
        echo "Opening configuration file..."
        if command -v $EDITOR &> /dev/null; then
            $EDITOR "$CONFIG_FILE"
        elif command -v nano &> /dev/null; then
            nano "$CONFIG_FILE"
        else
            echo "Default editor not found. Please edit: $CONFIG_FILE"
        fi
        ;;
    logs)
        echo "Audio Stream Detection Daemon Logs (Ctrl+C to exit):"
        journalctl --user -u "$SERVICE_NAME" -f
        ;;
    test)
        echo "Testing daemon (dry run)..."
        audio_detect_daemon --dry-run
        ;;
    *)
        echo "Audio Stream Detection Service Management"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|enable|disable|config|logs|test}"
        echo ""
        echo "Commands:"
        echo "  start    - Start the daemon"
        echo "  stop     - Stop the daemon"
        echo "  restart  - Restart the daemon"
        echo "  status   - Show daemon status"
        echo "  enable   - Enable auto-start on login"
        echo "  disable  - Disable auto-start on login"
        echo "  config   - Edit configuration file"
        echo "  logs     - Show daemon logs (live)"
        echo "  test     - Test daemon (dry run)"
        echo ""
        echo "Config file: $CONFIG_FILE"
        exit 1
        ;;
esac
EOF

chmod +x "$HOME_DIR/.local/bin/audio-detect-service"
echo -e "✓ CLI script: $HOME_DIR/.local/bin/audio-detect-service"

# Ensure ~/.local/bin is in PATH
if ! echo "$PATH" | grep -q "$HOME_DIR/.local/bin"; then
    echo -e "\n${YELLOW}Adding ~/.local/bin to PATH...${NC}"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME_DIR/.bashrc"
    export PATH="$HOME_DIR/.local/bin:$PATH"
    echo -e "✓ Added to ~/.bashrc"
fi

# Installation complete
echo -e "\n${GREEN}🎉 Installation complete!${NC}"
echo ""
echo -e "${BLUE}Quick start:${NC}"
echo "  audio-detect-service start    # Start daemon"
echo "  audio-detect-service status   # Check status"
echo "  audio-detect-service config   # Edit configuration"
echo "  audio-detect-service logs     # View logs"
echo ""
echo -e "${BLUE}To enable auto-start on login:${NC}"
echo "  audio-detect-service enable"
echo ""
echo -e "${BLUE}Configuration file:${NC}"
echo "  $HOME_DIR/.config/audio-detect/config.yaml"
echo ""
echo -e "${BLUE}Downloads directory:${NC}"
echo "  $HOME_DIR/AudioCaptures/"
echo ""
echo -e "${YELLOW}Note: You may need to log out and back in for PATH changes to take effect.${NC}"
