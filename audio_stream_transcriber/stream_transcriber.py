"""Main streaming transcription engine."""

import asyncio
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np
import typer
from rich.console import Console

from .audio_buffer import AudioBuffer
from .config import get_settings
from .mcp_client import WhisperMCPClient


class StreamTranscriber:
    """Real-time audio streaming transcriber."""
    
    def __init__(self):
        """Initialize the transcriber."""
        self.settings = get_settings()
        self.console = Console()
        
        # Components
        self.audio_buffer = AudioBuffer(
            chunk_duration=self.settings.chunk_duration_seconds,
            overlap=self.settings.overlap_seconds,
            sample_rate=self.settings.sample_rate,
            channels=self.settings.channels
        )
        
        self.mcp_client = WhisperMCPClient(
            server_path=Path(".") / "mcp-server-whisper"
        )
        
        # State
        self.running = False
        self.ffmpeg_process: Optional[subprocess.Popen] = None
        self.transcription_task: Optional[asyncio.Task] = None
        
        # Statistics
        self.total_chunks_processed = 0
        self.total_transcription_time = 0.0
        self.last_transcription = ""
        
    async def start_transcription(self) -> None:
        """Start the transcription process."""
        self.console.print("[green]Starting real-time transcription...[/green]")
        
        try:
            # Connect to MCP server
            await self.mcp_client.connect()
            self.console.print("[green]Connected to Whisper MCP server[/green]")
            
            # Start ffmpeg capture
            self._start_ffmpeg_capture()
            
            # Start transcription loop
            self.running = True
            self.transcription_task = asyncio.create_task(self._transcription_loop())
            
            # Wait for tasks to run (instead of blocking display)
            try:
                # Run until interrupted
                while True:
                    await asyncio.sleep(0.1)  # Brief sleep to avoid busy waiting
            except KeyboardInterrupt:
                self.console.print("\n[yellow]Stopping transcription...[/yellow]")
                await self.stop()
                
        except Exception as e:
            self.console.print(f"[red]Error starting transcription: {e}[/red]")
            await self.stop()
    
    def _start_ffmpeg_capture(self) -> None:
        """Start ffmpeg process for audio capture."""
        ffmpeg_cmd = [
            "ffmpeg",
            "-f", "pulse",
            "-i", self.settings.pulse_device,
            "-ac", str(self.settings.channels),
            "-ar", str(self.settings.sample_rate),
            "-f", "f32le",  # 32-bit float output
            "-"  # Output to stdout
        ]
        
        self.console.print(f"[blue]Starting ffmpeg: {' '.join(ffmpeg_cmd)}[/blue]")
        
        self.ffmpeg_process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0
        )
        
        # Start audio reading thread
        self.audio_thread = threading.Thread(target=self._read_audio_stream)
        self.audio_thread.daemon = True
        self.audio_thread.start()
    
    def _read_audio_stream(self) -> None:
        """Read audio data from ffmpeg stdout."""
        # Calculate bytes per sample
        bytes_per_sample = 4  # 32-bit float
        bytes_per_frame = bytes_per_sample * self.settings.channels
        
        while self.running and self.ffmpeg_process:
            try:
                # Read audio data
                data = self.ffmpeg_process.stdout.read(bytes_per_frame * 1024)  # Read 1024 frames
                if not data:
                    break
                
                # Convert to numpy array
                audio_data = np.frombuffer(data, dtype=np.float32)
                
                # Add to buffer
                self.audio_buffer.add_audio_data(audio_data)
                
            except Exception as e:
                if self.running:
                    self.console.print(f"[red]Audio read error: {e}[/red]")
                break
    
    async def _transcription_loop(self) -> None:
        """Main transcription processing loop."""
        self.console.print("[green]Transcription loop started[/green]")
        
        while self.running:
            try:
                # Get next audio chunk
                chunk_data = self.audio_buffer.get_next_chunk(timeout=1.0)
                if chunk_data is None:
                    continue
                
                chunk, timestamp = chunk_data
                self.total_chunks_processed += 1
                
                # Transcribe chunk
                start_time = time.time()
                result = await self.mcp_client.transcribe_audio(
                    audio_data=chunk,
                    sample_rate=self.settings.sample_rate
                )
                transcription_time = time.time() - start_time
                self.total_transcription_time += transcription_time
                
                # Update last transcription
                if result["text"].strip():
                    self.last_transcription = result["text"]
                    
                    # Display transcription with stats
                    self.console.print(f"[cyan]{timestamp:.1f}s:[/cyan] {result['text']}")
                    self.console.print(f"[dim]Latency: {transcription_time:.2f}s, Chunks: {self.total_chunks_processed}[/dim]")
                
            except Exception as e:
                self.console.print(f"[red]Transcription error: {e}[/red]")
                await asyncio.sleep(0.1)
    
    def _display_transcription(self) -> None:
        """Display live transcription output."""
        try:
            # Run event loop until interrupted
            asyncio.get_event_loop().run_forever()
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Stopping transcription...[/yellow]")
            asyncio.create_task(self.stop())
    
    async def stop(self) -> None:
        """Stop the transcription process."""
        self.console.print("[yellow]Stopping transcription...[/yellow]")
        
        self.running = False
        
        # Stop ffmpeg
        if self.ffmpeg_process:
            self.ffmpeg_process.terminate()
            self.ffmpeg_process.wait(timeout=5)
            self.ffmpeg_process = None
        
        # Stop transcription task
        if self.transcription_task:
            self.transcription_task.cancel()
            try:
                await self.transcription_task
            except asyncio.CancelledError:
                pass
        
        # Disconnect MCP client
        await self.mcp_client.disconnect()
        
        # Print statistics
        if self.total_chunks_processed > 0:
            avg_latency = self.total_transcription_time / self.total_chunks_processed
            self.console.print(f"[green]Processed {self.total_chunks_processed} chunks[/green]")
            self.console.print(f"[green]Average latency: {avg_latency:.2f}s[/green]")
        
        self.console.print("[green]Transcription stopped[/green]")
    
    def print_status(self) -> None:
        """Print current status information."""
        status = self.audio_buffer.get_buffer_status()
        self.console.print("[blue]Current Status:[/blue]")
        for key, value in status.items():
            self.console.print(f"  {key}: {value}")


app = typer.Typer(help="Real-time audio streaming transcription")


@app.command()
def start(
    device: Optional[str] = typer.Option(None, "--device", "-d", help="PulseAudio device name"),
    chunk_duration: Optional[float] = typer.Option(None, "--chunk-duration", help="Chunk duration in seconds"),
    overlap: Optional[float] = typer.Option(None, "--overlap", help="Overlap between chunks in seconds")
):
    """Start real-time transcription."""
    # Override settings if provided
    settings = get_settings()
    if device:
        settings.pulse_device = device
    if chunk_duration:
        settings.chunk_duration_seconds = chunk_duration
    if overlap:
        settings.overlap_seconds = overlap
    
    # Create and run transcriber
    transcriber = StreamTranscriber()
    
    # Set up signal handlers
    def signal_handler(signum, frame):
        asyncio.create_task(transcriber.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run transcription
    asyncio.run(transcriber.start_transcription())


@app.command()
def status():
    """Show current system status."""
    settings = get_settings()
    console = Console()
    
    console.print("[blue]Audio Stream Transcriber Status[/blue]")
    console.print(f"Device: {settings.pulse_device}")
    console.print(f"Chunk duration: {settings.chunk_duration_seconds}s")
    console.print(f"Overlap: {settings.overlap_seconds}s")
    console.print(f"Sample rate: {settings.sample_rate}")
    console.print(f"Channels: {settings.channels}")


if __name__ == "__main__":
    app()
