"""Circular buffer for managing audio chunks in real-time processing."""

import asyncio
import threading
import time
from collections import deque
from typing import Deque, Optional, Tuple

import numpy as np


class AudioBuffer:
    """Thread-safe circular buffer for audio chunks."""
    
    def __init__(
        self,
        chunk_duration: float,
        overlap: float,
        sample_rate: int,
        channels: int = 1,
        max_chunks: int = 10
    ):
        """Initialize audio buffer.
        
        Args:
            chunk_duration: Duration of each chunk in seconds
            overlap: Overlap between chunks in seconds
            sample_rate: Audio sample rate
            channels: Number of audio channels
            max_chunks: Maximum number of chunks to keep in memory
        """
        self.chunk_duration = chunk_duration
        self.overlap = overlap
        self.sample_rate = sample_rate
        self.channels = channels
        self.max_chunks = max_chunks
        
        # Calculate chunk sizes
        self.chunk_samples = int(chunk_duration * sample_rate)
        self.overlap_samples = int(overlap * sample_rate)
        self.step_samples = self.chunk_samples - self.overlap_samples
        
        # Initialize buffers
        self.audio_buffer: Deque[np.ndarray] = deque(maxlen=max_chunks)
        self.timestamp_buffer: Deque[float] = deque(maxlen=max_chunks)
        self.processed_buffer: Deque[Tuple[np.ndarray, float]] = deque(maxlen=max_chunks)
        
        # Thread safety
        self.lock = threading.Lock()
        self.data_available = threading.Condition(self.lock)
        
        # Current accumulation buffer
        self.accumulation_buffer = np.array([], dtype=np.float32)
        self.last_process_time = 0.0
        
    def add_audio_data(self, audio_data: np.ndarray) -> None:
        """Add new audio data to the buffer.
        
        Args:
            audio_data: New audio samples as numpy array
        """
        with self.lock:
            # Add to accumulation buffer
            self.accumulation_buffer = np.concatenate([self.accumulation_buffer, audio_data])
            
            # Check if we have enough data for a chunk
            current_time = time.time()
            if (len(self.accumulation_buffer) >= self.chunk_samples and 
                current_time - self.last_process_time >= self.chunk_duration):
                
                # Extract chunk
                chunk = self.accumulation_buffer[:self.chunk_samples].copy()
                
                # Store chunk and timestamp
                self.audio_buffer.append(chunk)
                self.timestamp_buffer.append(current_time)
                
                # Remove processed data (keep overlap)
                self.accumulation_buffer = self.accumulation_buffer[self.step_samples:]
                self.last_process_time = current_time
                
                # Notify waiting threads
                self.data_available.notify()
    
    def get_next_chunk(self, timeout: Optional[float] = None) -> Optional[Tuple[np.ndarray, float]]:
        """Get the next available audio chunk.
        
        Args:
            timeout: Maximum time to wait for data
            
        Returns:
            Tuple of (audio_chunk, timestamp) or None if timeout
        """
        with self.data_available:
            if not self.audio_buffer:
                self.data_available.wait(timeout)
                if not self.audio_buffer:
                    return None
            
            chunk = self.audio_buffer.popleft()
            timestamp = self.timestamp_buffer.popleft()
            
            # Store in processed buffer
            self.processed_buffer.append((chunk, timestamp))
            
            return chunk, timestamp
    
    def get_processed_chunks(self) -> list[Tuple[np.ndarray, float]]:
        """Get all processed chunks.
        
        Returns:
            List of (audio_chunk, timestamp) tuples
        """
        with self.lock:
            return list(self.processed_buffer)
    
    def clear(self) -> None:
        """Clear all buffers."""
        with self.lock:
            self.audio_buffer.clear()
            self.timestamp_buffer.clear()
            self.processed_buffer.clear()
            self.accumulation_buffer = np.array([], dtype=np.float32)
            self.last_process_time = 0.0
    
    def get_buffer_status(self) -> dict:
        """Get current buffer status.
        
        Returns:
            Dictionary with buffer statistics
        """
        with self.lock:
            return {
                "audio_buffer_size": len(self.audio_buffer),
                "processed_buffer_size": len(self.processed_buffer),
                "accumulation_buffer_samples": len(self.accumulation_buffer),
                "chunk_samples": self.chunk_samples,
                "overlap_samples": self.overlap_samples,
            }
