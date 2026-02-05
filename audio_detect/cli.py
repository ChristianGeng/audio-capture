"""Click CLI for audio stream detection."""

import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import click
from rich.console import Console
from rich.table import Table

from .core import (
    AudioStream,
    create_virtual_sink,
    generate_ffmpeg_command,
    has_pactl,
    has_wpctl,
    list_audio_streams,
    move_sink_input_to_sink,
)


console = Console()


@click.group()
@click.version_option()
def cli():
    """Audio detection CLI - Find and route browser/Teams audio streams."""
    if not has_pactl():
        console.print("[red]Error: pactl not found. Please install pulseaudio-utils.[/red]")
        sys.exit(1)


@cli.command()
@click.option("--teams-only", is_flag=True, help="Show only Teams streams")
@click.option(
    "--browser",
    type=click.Choice(["chrome", "edge", "firefox", "all"], case_sensitive=False),
    default="all",
    help="Filter by browser"
)
@click.option(
    "--format",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    help="Output format"
)
@click.option("--show-ffmpeg", is_flag=True, help="Include ffmpeg commands")
@click.option("--show-ids", is_flag=True, help="Show sink input IDs")
def list(teams_only: bool, browser: str, format: str, show_ffmpeg: bool, show_ids: bool):
    """List active audio streams."""
    streams = list_audio_streams()
    
    # Apply filters
    if teams_only:
        streams = [s for s in streams if s.is_teams]
    
    if browser != "all":
        browser_map = {
            "chrome": "google chrome",
            "edge": "microsoft edge", 
            "firefox": "firefox"
        }
        browser_term = browser_map.get(browser.lower(), browser.lower())
        streams = [s for s in streams if browser_term in s.application.lower()]
    
    if not streams:
        console.print("[yellow]No matching streams found.[/yellow]")
        return
    
    if format == "json":
        output = []
        for stream in streams:
            data = {
                "id": stream.id,
                "state": stream.state,
                "application": stream.application,
                "media": stream.media,
                "sink": stream.sink_name,
                "monitor": stream.monitor,
                "is_teams": stream.is_teams,
                "is_browser": stream.is_browser,
                "is_running": stream.is_running
            }
            if show_ffmpeg:
                data["ffmpeg"] = generate_ffmpeg_command(stream.monitor)
            output.append(data)
        console.print(json.dumps(output, indent=2))
    else:
        table = Table(title="Active Audio Streams")
        table.add_column("ID", justify="right", style="cyan", no_wrap=True)
        table.add_column("State", style="magenta")
        table.add_column("Application", style="green")
        table.add_column("Media", style="blue")
        table.add_column("Sink", style="yellow")
        table.add_column("Teams?", style="red")
        if show_ffmpeg:
            table.add_column("FFmpeg Command", style="dim")
        
        for stream in streams:
            row = [
                str(stream.id) if show_ids else "-",
                stream.state,
                stream.application[:20] + "..." if len(stream.application) > 20 else stream.application,
                stream.media[:30] + "..." if len(stream.media) > 30 else stream.media,
                stream.sink_name[:25] + "..." if len(stream.sink_name) > 25 else stream.sink_name,
                "✓" if stream.is_teams else "-"
            ]
            if show_ffmpeg:
                row.append(generate_ffmpeg_command(stream.monitor, "capture.wav"))
            table.add_row(*row)
        
        console.print(table)


@cli.command()
@click.option("--teams-only", is_flag=True, help="Show only Teams streams")
@click.option(
    "--browser",
    type=click.Choice(["chrome", "edge", "firefox", "all"], case_sensitive=False),
    default="all",
    help="Filter by browser"
)
def suggest(teams_only: bool, browser: str):
    """Show ffmpeg capture commands for active streams."""
    streams = list_audio_streams()
    
    # Apply filters
    if teams_only:
        streams = [s for s in streams if s.is_teams]
    
    if browser != "all":
        browser_map = {
            "chrome": "google chrome",
            "edge": "microsoft edge",
            "firefox": "firefox"
        }
        browser_term = browser_map.get(browser.lower(), browser.lower())
        streams = [s for s in streams if browser_term in s.application.lower()]
    
    if not streams:
        console.print("[yellow]No matching streams found.[/yellow]")
        return
    
    console.print("[bold green]FFmpeg Capture Commands:[/bold green]\n")
    
    for i, stream in enumerate(streams, 1):
        console.print(f"[cyan]{i}.[/cyan] [bold]{stream.application}[/bold] - {stream.media}")
        console.print(f"   Sink: {stream.sink_name}")
        console.print(f"   Monitor: {stream.monitor}")
        console.print(f"   Teams: {'✓' if stream.is_teams else '-'}")
        console.print(f"   Command: [dim]{generate_ffmpeg_command(stream.monitor)}[/dim]\n")


@cli.command()
@click.option("--id", "sink_input_id", required=True, type=int, help="Sink input ID to move")
@click.option(
    "--virtual-name",
    default="chrome_tab_sink",
    help="Virtual sink name"
)
@click.option("--create-virtual", is_flag=True, help="Create virtual sink if missing")
def route(sink_input_id: int, virtual_name: str, create_virtual: bool):
    """Route a sink input to a virtual sink for isolation."""
    # Verify the sink input exists
    streams = list_audio_streams()
    target_stream = None
    
    for stream in streams:
        if stream.id == sink_input_id:
            target_stream = stream
            break
    
    if not target_stream:
        console.print(f"[red]Error: Sink input {sink_input_id} not found.[/red]")
        console.print("Run 'audio-detect list --show-ids' to see available IDs.")
        sys.exit(1)
    
    console.print(f"[blue]Found stream:[/blue] {target_stream.application} - {target_stream.media}")
    
    # Create virtual sink if needed
    if create_virtual:
        console.print(f"[blue]Creating virtual sink: {virtual_name}[/blue]")
        if not create_virtual_sink(virtual_name):
            console.print(f"[red]Failed to create virtual sink {virtual_name}[/red]")
            sys.exit(1)
        console.print(f"[green]✓ Created virtual sink {virtual_name}[/green]")
    
    # Move the sink input
    console.print(f"[blue]Moving stream to {virtual_name}...[/blue]")
    if move_sink_input_to_sink(sink_input_id, virtual_name):
        console.print(f"[green]✓ Successfully moved stream to {virtual_name}[/green]")
        console.print(f"\n[dim]You can now capture with:[/dim]")
        console.print(f"[cyan]ffmpeg -f pulse -i {virtual_name}.monitor -ac 1 -ar 16000 output.wav[/cyan]")
    else:
        console.print(f"[red]Failed to move stream to {virtual_name}[/red]")
        sys.exit(1)


@cli.command()
def status():
    """Show system status and available tools."""
    console.print("[bold]Audio Detection System Status[/bold]\n")
    
    # Check tools
    console.print("Tools:")
    console.print(f"  pactl: {'✓' if has_pactl() else '✗'}")
    console.print(f"  wpctl: {'✓' if has_wpctl() else '✗'}")
    
    # Count streams
    streams = list_audio_streams()
    running = [s for s in streams if s.is_running]
    teams = [s for s in streams if s.is_teams]
    browsers = [s for s in streams if s.is_browser]
    
    console.print(f"\nStreams:")
    console.print(f"  Total: {len(streams)}")
    console.print(f"  Running: {len(running)}")
    console.print(f"  Teams: {len(teams)}")
    console.print(f"  Browsers: {len(browsers)}")
    
    # Show virtual sinks
    try:
        result = subprocess.run(
            ["pactl", "list", "sinks"],
            capture_output=True,
            text=True,
            check=True
        )
        virtual_sinks = []
        for line in result.stdout.split('\n'):
            if line.startswith('\tName: ') and 'null' in line.lower():
                virtual_sinks.append(line.split(': ')[1])
        
        console.print(f"\nVirtual Sinks: {len(virtual_sinks)}")
        for sink in virtual_sinks:
            console.print(f"  - {sink}")
    except subprocess.CalledProcessError:
        console.print("\nVirtual Sinks: Could not determine")


if __name__ == "__main__":
    cli()
