"""Core audio stream detection utilities."""

import re
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .detectors import AudioStateDetector

@dataclass
class AudioStream:
    """Represents an active audio stream."""
    id: int
    state: str
    application: str
    media: str
    sink: str
    sink_name: str
    monitor: str
    volume: str = "0%"
    is_teams: bool = False
    is_browser: bool = False
    last_activity: float = 0.0

    # Internal PulseAudio state (for detector use)
    _corked: bool = False
    _muted: bool = False

    def update_state(self, detector: 'AudioStateDetector') -> None:
        """Update state using the provided detector."""
        detector.update_stream_activity(self)
        self.state = detector.get_stream_state(self)

    @property
    def is_running(self) -> bool:
        return self.state == 'RUNNING'

    @property
    def is_active(self, detector: 'AudioStateDetector' = None) -> bool:
        """Check if stream is actively playing."""
        if detector:
            return detector.is_stream_active(self)

        # Fallback to basic state check
        import time
        current_time = time.time()

        # Consider stream idle if no activity for 5 seconds
        if self.last_activity > 0:
            return (current_time - self.last_activity) < 5.0

        # Fallback to state-based detection
        return self.state in ['RUNNING']


def has_wpctl() -> bool:
    """Check if wpctl is available."""
    try:
        subprocess.run(["wpctl", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def has_pactl() -> bool:
    """Check if pactl is available."""
    try:
        subprocess.run(["pactl", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def list_sink_inputs_pactl() -> list[dict]:
    """List sink inputs using pactl."""
    try:
        result = subprocess.run(
            ["pactl", "list", "sink-inputs"],
            capture_output=True,
            text=True,
            check=True
        )
        return _parse_pactl_sink_inputs(result.stdout)
    except subprocess.CalledProcessError:
        return []


def _parse_pactl_sink_inputs(output: str) -> list[dict]:
    """Parse pactl sink-inputs output."""
    streams = []
    current = {}

    for line in output.split('\n'):
        line = line.strip()

        # Start of new sink input
        if line.startswith('Sink Input #'):
            if current:
                streams.append(current)
            current = {'id': int(line.split('#')[1])}

        # Parse properties
        elif line.startswith('application.name = '):
            current['application'] = line.split('"')[1]
        elif line.startswith('media.name = '):
            current['media'] = line.split('"')[1]
        elif line.startswith('Sink: '):
            current['sink'] = line.split(': ')[1]
        elif line.startswith('Corked: '):
            current['corked'] = line.split(': ')[1] == 'yes'
        elif line.startswith('Mute: '):
            current['muted'] = line.split(': ')[1] == 'yes'
        elif line.startswith('Volume: '):
            # Extract volume percentage
            volume_part = line.split(': ')[1]
            if '%' in volume_part:
                current['volume'] = volume_part.split('%')[0] + '%'

    # Add the last one
    if current:
        streams.append(current)

    return streams


def list_streams_wpctl() -> list[dict]:
    """List streams using wpctl (PipeWire)."""
    try:
        result = subprocess.run(
            ["wpctl", "status"],
            capture_output=True,
            text=True,
            check=True
        )
        return _parse_wpctl_status(result.stdout)
    except subprocess.CalledProcessError:
        return []


def _parse_wpctl_status(output: str) -> list[dict]:
    """Parse wpctl status output to extract streams."""
    streams = []
    in_streams = False

    for line in output.split('\n'):
        if '└─ Streams:' in line:
            in_streams = True
            continue
        elif line.strip() and not line.startswith(' ') and not line.startswith('\t') and in_streams:
            in_streams = False
            continue

        if in_streams and line.strip():
            # Parse stream line
            # Format: "123. Google Chrome"
            if re.match(r'^\s*\d+\.', line):
                parts = line.strip().split(' ', 1)
                if len(parts) >= 2:
                    node_id = int(parts[0].rstrip('.'))
                    name = parts[1]
                    streams.append({
                        'id': node_id,
                        'name': name,
                        'state': 'RUNNING'  # wpctl only shows running streams
                    })

    return streams


def is_teams_stream(stream: dict) -> bool:
    """Check if a stream is likely Microsoft Teams."""
    app = stream.get('application', '').lower()
    media = stream.get('media', '').lower()
    name = stream.get('name', '').lower()

    teams_keywords = [
        'microsoft teams',
        'teams.microsoft.com',
        'teams meeting',
        'microsoft teams meeting'
    ]

    for keyword in teams_keywords:
        if (keyword in app or keyword in media or keyword in name):
            return True

    return False


def is_browser_stream(stream: dict) -> bool:
    """Check if a stream is from a browser."""
    app = stream.get('application', '').lower()
    name = stream.get('name', '').lower()

    browser_names = [
        'google chrome',
        'chromium',
        'microsoft edge',
        'firefox',
        'brave',
        'vivaldi'
    ]

    for browser in browser_names:
        if browser in app or browser in name:
            return True

    return False


def get_monitor_source(sink_name: str) -> str:
    """Get the monitor source name for a sink."""
    return f"{sink_name}.monitor"


def validate_monitor_source(monitor: str) -> bool:
    """Check if a monitor source exists."""
    try:
        result = subprocess.run(
            ["pactl", "list", "sources"],
            capture_output=True,
            text=True,
            check=True
        )
        return monitor in result.stdout
    except subprocess.CalledProcessError:
        return False


def merge_stream_data(pactl_streams: list[dict], wpctl_streams: list[dict]) -> list[AudioStream]:
    """Merge data from pactl and wpctl to create AudioStream objects."""
    streams = []

    # Create lookup by ID for wpctl streams
    wpctl_lookup = {s['id']: s for s in wpctl_streams}

    for pactl_stream in pactl_streams:
        stream_id = pactl_stream['id']

        # Merge with wpctl data if available
        wpctl_stream = wpctl_lookup.get(stream_id, {})

        # Determine state with better logic
        corked = pactl_stream.get('corked', False)
        muted = pactl_stream.get('mute', False)

        # Get state from wpctl if available, otherwise determine from pactl
        wpctl_state = wpctl_stream.get('state', '')

        if wpctl_state:
            state = wpctl_state
        elif corked:
            state = 'CORKED'
        elif muted:
            state = 'MUTED'
        else:
            # Check if actually running by looking at volume and other indicators
            volume = pactl_stream.get('volume', '0%')
            if '0%' in str(volume):
                state = 'IDLE'  # Exists but no audio
            else:
                state = 'RUNNING'  # Actively playing

        # Get sink name (convert from numeric ID if needed)
        sink = pactl_stream.get('sink', 'unknown')
        sink_name = sink
        if sink.isdigit():
            # Try to get sink name from pactl
            try:
                result = subprocess.run(
                    ["pactl", "list", "sinks"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                sink_name = _extract_sink_name(result.stdout, int(sink))
            except subprocess.CalledProcessError:
                sink_name = f"alsa_output.{sink}"

        monitor = get_monitor_source(sink_name)

        # Track activity - if stream is running, update timestamp
        import time
        current_time = time.time()
        last_activity = current_time if state == 'RUNNING' else 0.0

        # Store raw PulseAudio state for detectors
        corked = pactl_stream.get('corked', False)
        muted = pactl_stream.get('muted', False)

        monitor = get_monitor_source(sink_name)

        audio_stream = AudioStream(
            id=stream_id,
            state=state,
            application=pactl_stream.get('application', 'Unknown'),
            media=pactl_stream.get('media', 'Unknown'),
            sink=sink,
            sink_name=sink_name,
            monitor=monitor,
            volume=pactl_stream.get('volume', '0%'),
            is_teams=is_teams_stream(pactl_stream),
            is_browser=is_browser_stream(pactl_stream),
            last_activity=last_activity,
            _corked=corked,
            _muted=muted
        )

        streams.append(audio_stream)

    return streams


def _extract_sink_name(output: str, sink_id: int) -> str:
    """Extract sink name from pactl output by ID."""
    current_id = None
    current_name = None

    for line in output.split('\n'):
        if line.startswith(f'Sink #{sink_id}'):
            current_id = sink_id
        elif current_id is not None and line.startswith('\tName: '):
            current_name = line.split(': ')[1]
            break

    return current_name or f"unknown_sink_{sink_id}"


def list_audio_streams(detector_type: str = 'pulse') -> list[AudioStream]:
    """List all active audio streams using specified detector."""
    try:
        from .detectors import StateDetectorFactory
    except ImportError:
        # Fallback if detectors module not available
        from audio_detect.detectors import StateDetectorFactory
    
    # Get streams from PulseAudio
    pactl_streams = list_sink_inputs_pactl()
    wpctl_streams = list_streams_wpctl()
    streams = merge_stream_data(pactl_streams, wpctl_streams)
    
    # Apply state detection
    detector = StateDetectorFactory.create_detector(detector_type)
    for stream in streams:
        stream.update_state(detector)
    
    return streams


def create_virtual_sink(name: str = "chrome_tab_sink") -> bool:
    """Create a virtual null sink."""
    try:
        # Check if sink already exists
        result = subprocess.run(
            ["pactl", "list", "sinks"],
            capture_output=True,
            text=True,
            check=True
        )
        if name in result.stdout:
            return True

        # Create the sink
        subprocess.run(
            ["pactl", "load-module", "module-null-sink", f"sink_name={name}"],
            capture_output=True,
            check=True
        )
        return True
    except subprocess.CalledProcessError:
        return False


def move_sink_input_to_sink(sink_input_id: int, sink_name: str) -> bool:
    """Move a sink input to a specific sink."""
    try:
        subprocess.run(
            ["pactl", "move-sink-input", str(sink_input_id), sink_name],
            capture_output=True,
            check=True
        )
        return True
    except subprocess.CalledProcessError:
        return False


def generate_ffmpeg_command(monitor_source: str, output_file: str = "output.wav") -> str:
    """Generate an ffmpeg command for capturing from a monitor source."""
    return (
        f"ffmpeg -f pulse -i {monitor_source} "
        f"-ac 1 -ar 16000 {output_file}"
    )
