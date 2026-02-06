"""
Audio state detection interface and implementations.

This module provides an abstraction layer for different audio state detection
methods, allowing easy switching between PulseAudio, browser-based detection,
and hybrid approaches.
"""

import asyncio
import json
import logging
import time
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import websockets

from .core import AudioStream

logger = logging.getLogger(__name__)


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


@dataclass
class ChromeTab:
    """Represent a Chrome browser tab with audio state info."""

    id: str
    title: str
    url: str
    tab_type: str
    favicon_url: str = ""
    ws_url: str = ""
    has_audio: bool = False
    audio_state: str = "unknown"
    media_elements: list[dict[str, Any]] = field(default_factory=list)


# JS snippet injected into each tab to detect media playback
_MEDIA_DETECT_JS = """
(function() {
    var elems = document.querySelectorAll('audio, video');
    var results = [];
    for (var i = 0; i < elems.length; i++) {
        var el = elems[i];
        results.push({
            tag: el.tagName.toLowerCase(),
            paused: el.paused,
            muted: el.muted,
            volume: el.volume,
            currentTime: el.currentTime,
            duration: el.duration || 0,
            src: (el.currentSrc || el.src || '').substring(0, 120)
        });
    }
    return JSON.stringify(results);
})()
"""


class BrowserStateDetector(AudioStateDetector):
    """Browser-based state detection using Chrome DevTools Protocol."""

    def __init__(
        self,
        idle_timeout: float = 5.0,
        debug_port: int = 9222,
    ):
        self.idle_timeout = idle_timeout
        self.debug_port = debug_port
        self._chrome_connected = False
        self._tabs: list[ChromeTab] = []
        self._tab_states: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def list_tabs(self, with_audio_state: bool = True) -> list[ChromeTab]:
        """Return all Chrome page tabs, optionally enriched with audio state."""
        if not self._chrome_connected:
            if not self._connect_to_chrome():
                return []

        if with_audio_state:
            self._query_all_tab_audio()
        return [t for t in self._tabs if t.tab_type == "page"]

    # ------------------------------------------------------------------
    # Chrome DevTools HTTP API
    # ------------------------------------------------------------------

    def _connect_to_chrome(self) -> bool:
        """Fetch the tab list from Chrome DevTools HTTP endpoint."""
        url = f"http://localhost:{self.debug_port}/json"
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                data = json.loads(resp.read().decode())
        except Exception as exc:
            logger.debug(
                "Cannot reach Chrome DevTools at %s: %s", url, exc
            )
            self._chrome_connected = False
            return False

        self._tabs = []
        for entry in data:
            tab = ChromeTab(
                id=entry.get("id", ""),
                title=entry.get("title", ""),
                url=entry.get("url", ""),
                tab_type=entry.get("type", ""),
                favicon_url=entry.get("faviconUrl", ""),
                ws_url=entry.get("webSocketDebuggerUrl", ""),
            )
            self._tabs.append(tab)

        self._chrome_connected = True
        logger.debug("Connected to Chrome, found %d entries", len(self._tabs))
        return True

    # ------------------------------------------------------------------
    # Per-tab audio detection via WebSocket + Runtime.evaluate
    # ------------------------------------------------------------------

    def _query_all_tab_audio(self) -> None:
        """Query every page tab for audio/video element state."""
        asyncio.get_event_loop().run_until_complete(
            self._async_query_all()
        ) if self._has_running_loop() is False else (
            asyncio.ensure_future(self._async_query_all())
        )

    @staticmethod
    def _has_running_loop() -> bool:
        """Check whether an asyncio event loop is already running."""
        try:
            loop = asyncio.get_running_loop()
            return loop.is_running()
        except RuntimeError:
            return False

    async def _async_query_all(self) -> None:
        """Query all page tabs concurrently."""
        page_tabs = [t for t in self._tabs if t.tab_type == "page" and t.ws_url]
        tasks = [self._async_query_tab(tab) for tab in page_tabs]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _async_query_tab(self, tab: ChromeTab) -> None:
        """Connect to one tab via WebSocket and evaluate media JS."""
        try:
            async with websockets.connect(
                tab.ws_url,
                open_timeout=2,
                close_timeout=1,
            ) as ws:
                msg = json.dumps({
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {"expression": _MEDIA_DETECT_JS},
                })
                await ws.send(msg)
                resp_raw = await asyncio.wait_for(ws.recv(), timeout=3)
                resp = json.loads(resp_raw)

                result_value = (
                    resp.get("result", {})
                    .get("result", {})
                    .get("value", "[]")
                )
                elements = json.loads(result_value)
                tab.media_elements = elements

                # Derive aggregate audio state
                if not elements:
                    tab.has_audio = False
                    tab.audio_state = "silent"
                else:
                    playing = [
                        e for e in elements
                        if not e.get("paused", True)
                    ]
                    muted = all(
                        e.get("muted", False) for e in elements
                    )
                    if playing and not muted:
                        tab.has_audio = True
                        tab.audio_state = "playing"
                    elif playing and muted:
                        tab.has_audio = True
                        tab.audio_state = "muted"
                    else:
                        tab.has_audio = False
                        tab.audio_state = "paused"

        except Exception as exc:
            logger.debug(
                "Failed to query tab '%s': %s", tab.title[:40], exc
            )
            tab.audio_state = "error"

    # ------------------------------------------------------------------
    # Stream-level helpers used by AudioStateDetector interface
    # ------------------------------------------------------------------

    def _get_tab_audio_state(self, stream: AudioStream) -> str:
        """Find the best-matching tab for a stream and return its state."""
        if not self._tabs:
            return "unknown"

        # Heuristic: if the stream is from a browser, look for
        # tabs that have active audio.  We cannot map PulseAudio
        # sink-input IDs to specific Chrome tabs, so we return
        # the "best" state across all tabs.
        playing_tabs = [
            t for t in self._tabs
            if t.tab_type == "page" and t.audio_state == "playing"
        ]
        if playing_tabs:
            return "playing"

        muted_tabs = [
            t for t in self._tabs
            if t.tab_type == "page" and t.audio_state == "muted"
        ]
        if muted_tabs:
            return "muted"

        paused_tabs = [
            t for t in self._tabs
            if t.tab_type == "page" and t.audio_state == "paused"
        ]
        if paused_tabs:
            return "paused"

        return "unknown"

    def get_stream_state(self, stream: AudioStream) -> str:
        """Determine state using browser information."""
        if not self._chrome_connected:
            if not self._connect_to_chrome():
                # Fallback to basic detection
                return 'RUNNING' if stream.volume != '0%' else 'IDLE'

        self._query_all_tab_audio()
        browser_state = self._get_tab_audio_state(stream)

        # Map browser states to our states
        state_mapping = {
            'playing': 'RUNNING',
            'paused': 'CORKED',
            'muted': 'MUTED',
            'silent': 'IDLE',
            'unknown': 'IDLE',
            'error': 'IDLE',
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
