"""
Audio state detection interface and implementations.

This module provides an abstraction layer for different audio state detection
methods, allowing easy switching between PulseAudio, browser-based detection,
and hybrid approaches.
"""

import time
from abc import ABC, abstractmethod
from typing import Any

from .core import AudioStream


class AudioStateDetector(ABC):
    """Abstract interface for audio state detection."""

    @abstractmethod
    def get_stream_state(self, stream: AudioStream) -> str:
        """
        Determine the current state of an audio stream.

        Args:
            stream: AudioStream to analyze

        Returns:
            State string: 'RUNNING', 'CORKED', 'MUTED', 'IDLE'
        """
        pass

    @abstractmethod
    def is_stream_active(self, stream: AudioStream) -> bool:
        """
        Check if a stream is actively producing audio.

        Args:
            stream: AudioStream to analyze

        Returns:
            True if stream is actively playing audio
        """
        pass

    @abstractmethod
    def update_stream_activity(self, stream: AudioStream) -> None:
        """
        Update the stream's activity tracking information.

        Args:
            stream: AudioStream to update
        """
        pass


class PulseAudioStateDetector(AudioStateDetector):
    """PulseAudio-based state detection using pactl/wpctl data."""

    def __init__(self, idle_timeout: float = 5.0):
        self.idle_timeout = idle_timeout

    def get_stream_state(self, stream: AudioStream) -> str:
        """Determine state using PulseAudio indicators."""
        # Use corked state as primary indicator
        if hasattr(stream, '_corked') and stream._corked:
            return 'CORKED'

        # Use muted state
        if hasattr(stream, '_muted') and stream._muted:
            return 'MUTED'

        # Check activity timing
        if stream.last_activity > 0:
            current_time = time.time()
            if (current_time - stream.last_activity) > self.idle_timeout:
                return 'IDLE'

        # Use volume as fallback (but be more lenient)
        volume_str = stream.volume or '0%'
        try:
            volume_num = int(''.join(filter(str.isdigit, volume_str)))
            if volume_num == 0:
                return 'IDLE'
        except (ValueError, AttributeError):
            pass  # Ignore volume parsing errors

        # Default to running if no other indicators
        return 'RUNNING'

    def is_stream_active(self, stream: AudioStream) -> bool:
        """Check if stream is actively playing."""
        state = self.get_stream_state(stream)
        return state == 'RUNNING'

    def update_stream_activity(self, stream: AudioStream) -> None:
        """Update activity timestamp for running streams."""
        if self.get_stream_state(stream) == 'RUNNING':
            stream.last_activity = time.time()


class BrowserStateDetector(AudioStateDetector):
    """Browser-based state detection using Chrome DevTools Protocol."""

    def __init__(self, idle_timeout: float = 5.0):
        self.idle_timeout = idle_timeout
        self._chrome_connected = False
        self._tab_states: dict[str, dict[str, Any]] = {}

    def _connect_to_chrome(self) -> bool:
        """Connect to Chrome DevTools Protocol."""
        # TODO: Implement Chrome DevTools connection
        # This would involve:
        # 1. Finding Chrome debugging port
        # 2. WebSocket connection to DevTools
        # 3. Enabling runtime domains
        return False

    def _get_tab_audio_state(self, stream: AudioStream) -> str:
        """Get audio state from browser tab."""
        # TODO: Implement browser state detection
        # This would involve:
        # 1. Matching stream to browser tab
        # 2. Querying tab media state via DevTools
        # 3. Returning actual playing/paused state
        return 'UNKNOWN'

    def get_stream_state(self, stream: AudioStream) -> str:
        """Determine state using browser information."""
        if not self._chrome_connected:
            if not self._connect_to_chrome():
                # Fallback to basic detection
                return 'RUNNING' if stream.volume != '0%' else 'IDLE'

        browser_state = self._get_tab_audio_state(stream)

        # Map browser states to our states
        state_mapping = {
            'playing': 'RUNNING',
            'paused': 'CORKED',
            'muted': 'MUTED',
            'unknown': 'IDLE'
        }

        return state_mapping.get(browser_state.lower(), 'IDLE')

    def is_stream_active(self, stream: AudioStream) -> bool:
        """Check if stream is actively playing via browser state."""
        return self.get_stream_state(stream) == 'RUNNING'

    def update_stream_activity(self, stream: AudioStream) -> None:
        """Update activity based on browser state."""
        if self.is_stream_active(stream):
            stream.last_activity = time.time()


class HybridStateDetector(AudioStateDetector):
    """Hybrid detector combining PulseAudio and browser detection."""

    def __init__(self, idle_timeout: float = 5.0):
        self.pulse_detector = PulseAudioStateDetector(idle_timeout)
        self.browser_detector = BrowserStateDetector(idle_timeout)
        self.idle_timeout = idle_timeout

    def get_stream_state(self, stream: AudioStream) -> str:
        """Determine state using both PulseAudio and browser data."""
        # Try browser detection first (more accurate)
        browser_state = self.browser_detector.get_stream_state(stream)
        if browser_state != 'UNKNOWN':
            return browser_state

        # Fallback to PulseAudio
        return self.pulse_detector.get_stream_state(stream)

    def is_stream_active(self, stream: AudioStream) -> bool:
        """Check if stream is active using hybrid approach."""
        return self.get_stream_state(stream) == 'RUNNING'

    def update_stream_activity(self, stream: AudioStream) -> None:
        """Update activity using both detectors."""
        if self.is_stream_active(stream):
            stream.last_activity = time.time()


class StateDetectorFactory:
    """Factory for creating appropriate state detectors."""

    @staticmethod
    def create_detector(detector_type: str, **kwargs) -> AudioStateDetector:
        """
        Create a state detector of the specified type.

        Args:
            detector_type: 'pulse', 'browser', 'hybrid'
            **kwargs: Additional arguments for detector

        Returns:
            AudioStateDetector instance
        """
        detectors = {
            'pulse': PulseAudioStateDetector,
            'browser': BrowserStateDetector,
            'hybrid': HybridStateDetector
        }

        if detector_type not in detectors:
            raise ValueError(f"Unknown detector type: {detector_type}")

        return detectors[detector_type](**kwargs)

    @staticmethod
    def get_available_detectors() -> list:
        """Get list of available detector types."""
        return ['pulse', 'browser', 'hybrid']
