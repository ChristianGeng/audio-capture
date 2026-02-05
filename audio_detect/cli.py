"""Click CLI for audio stream detection."""

import json
import subprocess
import sys
import time

import click
from rich.console import Console
from rich.table import Table

from .core import (
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
    "--detector",
    type=click.Choice(["pulse", "browser", "hybrid"], case_sensitive=False),
    default="pulse",
    help="State detection method"
)
@click.option(
    "--format",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    help="Output format"
)
@click.option("--show-ffmpeg", is_flag=True, help="Include ffmpeg commands")
@click.option("--show-ids", is_flag=True, help="Show sink input IDs")
def list(teams_only: bool, browser: str, detector: str, format: str, show_ffmpeg: bool, show_ids: bool):
    """List active audio streams."""
    streams = list_audio_streams(detector_type=detector)

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
        stream_data = []
        for stream in streams:
            data = {
                "id": stream.id,
                "state": stream.state,
                "application": stream.application,
                "media": stream.media,
                "sink": stream.sink_name,
                "monitor": stream.monitor,
                "volume": stream.volume,
                "is_teams": stream.is_teams,
            }
            if show_ffmpeg:
                data["ffmpeg"] = generate_ffmpeg_command(stream.monitor)
            stream_data.append(data)
        console.print(json.dumps(stream_data, indent=2))
        return

    # Table format
    table = Table(title="Active Audio Streams")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("State", style="green")
    table.add_column("Application", style="magenta")
    table.add_column("Media", style="yellow")
    table.add_column("Sink", style="blue")
    table.add_column("Volume", style="red")
    if show_ids:
        table.add_column("Sink ID", style="dim")
    if show_ffmpeg:
        table.add_column("FFmpeg", style="dim", max_width=50)
    if teams_only or browser != "all":
        table.add_column("Teams?", style="red")

    for stream in streams:
        state_style = {
            'RUNNING': 'green',
            'CORKED': 'yellow',
            'MUTED': 'red',
            'IDLE': 'dim'
        }.get(stream.state, 'white')

        # Add activity info for debugging
        activity_info = ""
        if stream.last_activity > 0:
            seconds_ago = int(time.time() - stream.last_activity)
            if seconds_ago < 60:
                activity_info = f" ({seconds_ago}s ago)"
            else:
                minutes_ago = seconds_ago // 60
                activity_info = f" ({minutes_ago}m ago)"

        row = [
            str(stream.id),
            f"[{state_style}]{stream.state}[/{state_style}]{activity_info}",
            stream.application,
            stream.media,
            stream.sink_name,  # Show full sink name for copy-paste
            stream.volume
        ]

        if show_ids:
            row.append(stream.sink)
        if show_ffmpeg:
            cmd = generate_ffmpeg_command(stream.monitor)
            row.append(cmd[:47] + "..." if len(cmd) > 50 else cmd)
        if teams_only or browser != "all":
            row.append("✓" if stream.is_teams else "-")

        table.add_row(*row)

    console.print(table)
    
    # Add generic ffmpeg example for the first stream
    if streams and format == "table":
        first_stream = streams[0]
        console.print("\n[bold]FFmpeg Example:[/bold]")
        console.print(f"[dim]# Capture audio from {first_stream.application}[/dim]")
        console.print(f"[green]ffmpeg -f pulse -i {first_stream.monitor} -ac 1 -ar 16000 capture.wav[/green]")
        console.print(f"[dim]# Monitor device: {first_stream.monitor}[/dim]")


@cli.command()
@click.option("--teams-only", is_flag=True, help="Show only Teams streams")
@click.option(
    "--browser",
    type=click.Choice(["chrome", "edge", "firefox", "all"], case_sensitive=False),
    default="all",
    help="Filter by browser"
)
@click.option(
    "--detector",
    type=click.Choice(["pulse", "browser", "hybrid"], case_sensitive=False),
    default="pulse",
    help="State detection method"
)
def suggest(teams_only: bool, browser: str, detector: str):
    """Show ffmpeg capture commands for active streams."""
    streams = list_audio_streams(detector_type=detector)
    
    # Simple active filter - just check if state is RUNNING
    active_streams = [s for s in streams if s.state == 'RUNNING']

    if not active_streams:
        if streams:
            console.print("[yellow]No actively playing streams found.[/yellow]")
            console.print("[dim]Found streams but they are paused/corked:[/dim]")
            for stream in streams:
                console.print(f"  • {stream.application} - {stream.media} ([{stream.state}])")
        else:
            console.print("[yellow]No matching streams found.[/yellow]")
        return

    console.print("[bold green]FFmpeg Capture Commands for Active Streams:[/bold green]\n")

    for i, stream in enumerate(active_streams, 1):
        console.print(f"[cyan]{i}.[/cyan] [bold]{stream.application}[/bold] - {stream.media}")
        console.print(f"   State: [green]{stream.state}[/green] | Volume: [yellow]{stream.volume}[/yellow]")
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
        console.print("\n[dim]You can now capture with:[/dim]")
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

    console.print("\nStreams:")
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
