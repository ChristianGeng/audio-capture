#!/usr/bin/env python3
"""Chrome Tab Audio Capture and Diarization Tool."""

import asyncio
import os
import subprocess
import time
from pathlib import Path

import numpy as np
import typer
from rich.console import Console

from audio_stream_transcriber.mcp_client import WhisperMCPClient

app = typer.Typer(help="Chrome tab audio capture, diarization, and transcription")


class ChromeTabCapturer:
    """Captures audio from Chrome tabs with diarization and transcription."""

    def __init__(self):
        """Initialize the capturer."""
        self.console = Console()
        self.virtual_sink = "chrome_tab_sink"
        self.monitor_source = f"{self.virtual_sink}.monitor"
        self.current_tab_name = "Unknown Tab"

    def setup_virtual_sink(self) -> bool:
        """Set up PulseAudio virtual sink for Chrome tab isolation."""
        try:
            # Check if sink already exists
            result = subprocess.run(
                ["pactl", "list", "sinks"],
                capture_output=True,
                text=True
            )
            if self.virtual_sink in result.stdout:
                self.console.print(f"[green]Virtual sink '{self.virtual_sink}' already exists[/green]")
                return True

            # Create virtual sink
            self.console.print(f"[blue]Creating virtual sink '{self.virtual_sink}'...[/blue]")
            result = subprocess.run([
                "pactl", "load-module", "module-null-sink",
                f"sink_name={self.virtual_sink}",
                "sink_properties=device.description=Chrome_Tab_Audio"
            ], capture_output=True, text=True)

            if result.returncode == 0:
                self.console.print(f"[green]Virtual sink '{self.virtual_sink}' created successfully[/green]")
                return True
            else:
                self.console.print(f"[red]Failed to create virtual sink: {result.stderr}[/red]")
                return False

        except Exception as e:
            self.console.print(f"[red]Error setting up virtual sink: {e}[/red]")
            return False

    def show_routing_instructions(self) -> None:
        """Show instructions for routing Chrome audio to virtual sink."""
        self.console.print("\n[bold blue]Chrome Audio Routing Instructions:[/bold blue]")
        self.console.print("1. Open PulseAudio Volume Control (pavucontrol)")
        self.console.print("2. Go to the 'Playback' tab")
        self.console.print("3. Find your Chrome tab/application")
        self.console.print(f"4. Change its output to: '[bold green]{self.virtual_sink}[/bold green]'")
        self.console.print("5. Start playing audio in your Chrome tab")
        self.console.print("6. Return here and press Enter to continue\n")

        # Ask for tab name
        self.current_tab_name = typer.prompt("Enter the name of the Chrome tab you're capturing", default="Chrome Tab")
        self.console.print(f"[green]📺 Capturing from tab: {self.current_tab_name}[/green]\n")

    def capture_audio(
        self,
        duration: int = 30,
        output_file: str | None = None
    ) -> Path | None:
        """Capture audio from the virtual sink."""
        if output_file is None:
            timestamp = int(time.time())
            output_file = f"{self.current_tab_name.replace(' ', '_').lower()}_{timestamp}.wav"

        output_path = Path(output_file)
        self.console.print(f"[blue]🎙️  Capturing audio from '{self.current_tab_name}' for {duration} seconds...[/blue]")
        self.console.print(f"[dim]Output: {output_path}[/dim]")

        try:
            # ffmpeg command to capture from virtual sink monitor
            cmd = [
                "ffmpeg",
                "-f", "pulse",
                "-i", self.monitor_source,
                "-ac", "1",  # Mono
                "-ar", "16000",  # 16kHz for better diarization
                "-t", str(duration),  # Duration
                "-y",  # Overwrite
                str(output_path)
            ]

            self.console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=duration + 5
            )

            if result.returncode == 0 and output_path.exists():
                file_size = output_path.stat().st_size
                self.console.print(f"[green]Audio captured successfully![/green]")
                self.console.print(f"[dim]File size: {file_size} bytes[/dim]")
                return output_path
            else:
                self.console.print(f"[red]Capture failed: {result.stderr}[/red]")
                return None

        except subprocess.TimeoutExpired:
            self.console.print("[yellow]Capture timed out[/yellow]")
            return None
        except Exception as e:
            self.console.print(f"[red]Error during capture: {e}[/red]")
            return None


class DiarizationTranscriber:
    """Handles diarization and transcription of captured audio."""

    def __init__(self):
        """Initialize the transcriber."""
        self.console = Console()
        self.mcp_client = WhisperMCPClient(
            server_path=Path(".") / "mcp-server-whisper"
        )

    async def setup_mcp(self) -> bool:
        """Set up the MCP client."""
        try:
            await self.mcp_client.connect()
            self.console.print("[green]Connected to Whisper MCP server[/green]")
            return True
        except Exception as e:
            self.console.print(f"[red]Failed to connect to MCP server: {e}[/red]")
            return False

    async def transcribe_audio(self, audio_file: Path) -> dict:
        """Transcribe audio file."""
        try:
            # Load audio
            import wave
            with wave.open(str(audio_file), 'rb') as wav:
                audio_data = np.frombuffer(wav.readframes(-1), dtype=np.int16).astype(np.float32) / 32767

            # Transcribe
            result = await self.mcp_client.transcribe_audio(
                audio_data=audio_data,
                sample_rate=16000
            )

            return result

        except Exception as e:
            self.console.print(f"[red]Transcription error: {e}[/red]")
            return {"text": "", "error": str(e)}

    def diarize_audio(self, audio_file: Path) -> dict:
        """Perform speaker diarization on audio file."""
        try:
            # Import pyannote.audio components
            from pyannote.audio import Pipeline

            # Use pyannote diarization pipeline
            # Note: This requires a HuggingFace token and model access
            self.console.print("[blue]Loading diarization model...[/blue]")

            # Use the speaker diarization pipeline
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=os.getenv("HUGGINGFACE_TOKEN")  # User needs to set this
            )

            # Run diarization
            self.console.print("[blue]Running speaker diarization...[/blue]")
            diarization = pipeline(str(audio_file))

            # Convert to our format
            speakers = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                speakers.append({
                    "speaker": speaker,
                    "start": turn.start,
                    "end": turn.end
                })

            self.console.print(f"[green]Found {len(set(s['speaker'] for s in speakers))} speakers[/green]")

            return {"speakers": speakers}

        except ImportError:
            self.console.print("[yellow]pyannote.audio not installed - using placeholder diarization[/yellow]")
            return self._placeholder_diarization(audio_file)
        except Exception as e:
            self.console.print(f"[red]Diarization error: {e}[/red]")
            return self._placeholder_diarization(audio_file)

    def _placeholder_diarization(self, audio_file: Path) -> dict:
        """Placeholder diarization when pyannote is not available."""
        # Simple placeholder: alternate speakers every 10 seconds
        import wave
        try:
            with wave.open(str(audio_file), 'rb') as wav:
                duration = wav.getnframes() / wav.getframerate()

            speakers = []
            current_time = 0.0
            speaker_num = 1

            while current_time < duration:
                end_time = min(current_time + 10.0, duration)
                speakers.append({
                    "speaker": f"SPEAKER_{speaker_num:02d}",
                    "start": current_time,
                    "end": end_time
                })
                current_time = end_time
                speaker_num = 1 if speaker_num == 2 else 2

            return {"speakers": speakers}

        except Exception as e:
            return {"speakers": [], "error": str(e)}

    async def process_audio(self, audio_file: Path) -> dict:
        """Process audio: transcribe and diarize."""
        self.console.print(f"[blue]Processing {audio_file}...[/blue]")

        # Transcribe
        transcription = await self.transcribe_audio(audio_file)

        # Diarize
        diarization = self.diarize_audio(audio_file)

        return {
            "transcription": transcription,
            "diarization": diarization,
            "audio_file": str(audio_file)
        }

    def combine_transcription_diarization(self, transcription_result: dict, diarization_result: dict) -> str:
        """Combine transcription with diarization for speaker-attributed output."""
        try:
            text = transcription_result.get("text", "")
            speakers = diarization_result.get("speakers", [])

            if not speakers:
                return f"Full transcript: {text}"

            # This is a simplified combination - in practice you'd need timestamped transcription
            # For now, just format with speaker labels
            output_lines = []
            current_speaker = None
            speaker_text = ""

            for speaker_info in speakers:
                speaker = speaker_info["speaker"]
                start = speaker_info["start"]
                end = speaker_info["end"]

                # Extract text segment (simplified - would need timestamped transcription)
                duration = end - start
                estimated_chars = int(duration * 15)  # Rough estimate: 15 chars/second speaking
                segment_text = text[:estimated_chars] if text else ""
                text = text[estimated_chars:] if text else ""

                if segment_text.strip():
                    if speaker != current_speaker:
                        if speaker_text:
                            output_lines.append(f"**{current_speaker}:** {speaker_text.strip()}")
                        current_speaker = speaker
                        speaker_text = segment_text
                    else:
                        speaker_text += " " + segment_text

            # Add final speaker
            if speaker_text:
                output_lines.append(f"**{current_speaker}:** {speaker_text.strip()}")

            # Add any remaining text
            if text.strip():
                output_lines.append(f"**{current_speaker or 'SPEAKER_UNKNOWN'}:** {text.strip()}")

            return "\n\n".join(output_lines)

        except Exception as e:
            self.console.print(f"[red]Error combining results: {e}[/red]")
            return f"Full transcript: {transcription_result.get('text', '')}"

    async def process_and_display_results(self, audio_file: Path) -> None:
        """Process audio and display speaker-attributed transcription."""
        result = await self.process_audio(audio_file)

        # Combine results
        speaker_attributed_text = self.combine_transcription_diarization(
            result["transcription"],
            result["diarization"]
        )

        # Display results
        console = Console()
        console.print("\n[bold blue]🎤 Chrome Tab Audio Analysis Complete![/bold blue]")
        console.print(f"[dim]Tab: {self.current_tab_name}[/dim]")
        console.print(f"[dim]File: {result['audio_file']}[/dim]")
        console.print(f"[dim]Transcription: {len(result['transcription'].get('text', ''))} chars[/dim]")
        console.print(f"[dim]Speakers detected: {len(set(s['speaker'] for s in result['diarization'].get('speakers', [])))}[/dim]")
        console.print("\n[bold green]📝 Speaker-Attributed Transcript:[/bold green]\n")
        console.print(speaker_attributed_text)

        # Save to file
        output_file = audio_file.with_suffix(".transcript.txt")
        with open(output_file, "w") as f:
            f.write(f"Audio File: {result['audio_file']}\n")
            f.write(f"Speakers Detected: {len(set(s['speaker'] for s in result['diarization'].get('speakers', [])))}\n\n")
            f.write("Speaker-Attributed Transcript:\n")
            f.write("=" * 50 + "\n\n")
            f.write(speaker_attributed_text)

        console.print(f"\n[green]💾 Saved to: {output_file}[/green]")


@app.command()
def setup():
    """Set up PulseAudio virtual sink for Chrome tab audio isolation."""
    capturer = ChromeTabCapturer()
    if capturer.setup_virtual_sink():
        capturer.show_routing_instructions()
    else:
        typer.echo("Failed to set up virtual sink")


@app.command()
def capture(
    duration: int = typer.Option(30, "--duration", "-d", help="Capture duration in seconds"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path")
):
    """Capture audio from Chrome tab."""
    capturer = ChromeTabCapturer()

    if not capturer.setup_virtual_sink():
        typer.echo("Failed to set up virtual sink")
        return

    typer.echo("Make sure Chrome audio is routed to the virtual sink, then press Enter...")
    input()

    audio_file = capturer.capture_audio(duration, output)
    if audio_file:
        typer.echo("Audio captured: " + str(audio_file))
    else:
        typer.echo("Audio capture failed")


@app.command()
def process(audio_file: str = typer.Argument(..., help="Path to audio file to process")):
    """Process captured audio: diarize and transcribe with speaker attribution."""
    transcriber = DiarizationTranscriber()

    async def run():
        if await transcriber.setup_mcp():
            await transcriber.process_and_display_results(Path(audio_file))

    asyncio.run(run())


@app.command()
def workflow(duration: int = typer.Option(30, "--duration", "-d", help="Capture duration")):
    """Complete workflow: setup -> capture -> process."""
    console = Console()

    # Setup
    console.print("[bold blue]Step 1: Setting up virtual sink[/bold blue]")
    capturer = ChromeTabCapturer()
    if not capturer.setup_virtual_sink():
        console.print("[red]Setup failed[/red]")
        return

    # Instructions
    capturer.show_routing_instructions()
    input("Press Enter when Chrome audio is routed...")

    # Capture
    console.print("[bold blue]Step 2: Capturing audio[/bold blue]")
    audio_file = capturer.capture_audio(duration)
    if not audio_file:
        console.print("[red]Capture failed[/red]")
        return

    # Process
    console.print("[bold blue]Step 3: Processing audio[/bold blue]")
    transcriber = DiarizationTranscriber()

    async def process():
        if await transcriber.setup_mcp():
            result = await transcriber.process_audio(audio_file)
            console.print("\n[bold green]Complete![/bold green]")
            console.print(f"Audio file: {result['audio_file']}")
            console.print(f"Transcription: {result['transcription'].get('text', 'No text')[:100]}...")

    asyncio.run(process())


if __name__ == "__main__":
    app()
