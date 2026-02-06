"""Click CLI for audio stream detection."""

import asyncio
import json
import subprocess
import sys
import time
from datetime import datetime

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
    shorten_sink_name,
)
from .detectors import BrowserStateDetector
from .teams_tracker import TeamsTracker

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
@click.option("--wide", is_flag=True, help="Show full sink names instead of shortened")
def list(teams_only: bool, browser: str, detector: str, format: str, show_ffmpeg: bool, show_ids: bool, wide: bool):
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
        is_active = stream.state == 'RUNNING'
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

        # Shorten sink name unless --wide is set
        sink_display = (
            stream.sink_name if wide
            else shorten_sink_name(stream.sink_name)
        )

        # Highlight active streams
        id_display = (
            f"[bold green]>>> {stream.id}[/bold green]"
            if is_active
            else str(stream.id)
        )

        row = [
            id_display,
            f"[{state_style}]{stream.state}[/{state_style}]{activity_info}",
            stream.application,
            stream.media,
            sink_display,
            stream.volume
        ]

        if show_ids:
            row.append(stream.sink)
        if show_ffmpeg:
            cmd = generate_ffmpeg_command(stream.monitor)
            row.append(cmd[:47] + "..." if len(cmd) > 50 else cmd)
        if teams_only or browser != "all":
            row.append("\u2713" if stream.is_teams else "-")

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
@click.option(
    "--port",
    default=9222,
    type=int,
    help="Chrome remote debugging port",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    help="Output format",
)
def tabs(port: int, fmt: str):
    """List Chrome tabs and their audio playback state.

    Requires Chrome running with --remote-debugging-port.
    """
    detector = BrowserStateDetector(debug_port=port)
    tab_list = detector.list_tabs(with_audio_state=True)

    if not tab_list:
        console.print(
            "[yellow]No Chrome tabs found.[/yellow]\n"
            "[dim]Start Chrome with: "
            "google-chrome --remote-debugging-port=9222[/dim]"
        )
        return

    if fmt == "json":
        data = []
        for tab in tab_list:
            entry = {
                "id": tab.id,
                "title": tab.title,
                "url": tab.url,
                "audio_state": tab.audio_state,
                "has_audio": tab.has_audio,
                "media_elements": tab.media_elements,
            }
            data.append(entry)
        console.print(json.dumps(data, indent=2))
        return

    table = Table(title="Chrome Tabs")
    table.add_column("Audio", style="bold", no_wrap=True)
    table.add_column("Title", style="magenta")
    table.add_column("URL", style="blue", max_width=60)
    table.add_column("Media", style="dim")

    state_icons = {
        "playing": "[bold green]\u266b playing[/bold green]",
        "muted": "[yellow]\u266b muted[/yellow]",
        "paused": "[dim]\u23f8 paused[/dim]",
        "silent": "[dim]- silent[/dim]",
        "error": "[red]? error[/red]",
        "unknown": "[dim]? unknown[/dim]",
    }

    for tab in tab_list:
        icon = state_icons.get(tab.audio_state, tab.audio_state)
        media_info = ""
        if tab.media_elements:
            count = len(tab.media_elements)
            playing = sum(
                1 for e in tab.media_elements
                if not e.get("paused", True)
            )
            media_info = (
                f"{playing}/{count} playing"
                if playing
                else f"{count} paused"
            )

        url_short = tab.url[:57] + "..." if len(tab.url) > 60 else tab.url
        table.add_row(icon, tab.title[:50], url_short, media_info)

    console.print(table)


@cli.command()
@click.option(
    "--port",
    default=9222,
    type=int,
    help="Chrome remote debugging port",
)
@click.option(
    "--interval",
    default=2.0,
    type=float,
    help="Seconds between polls",
)
@click.option(
    "--output", "-o",
    default=None,
    type=click.Path(),
    help="JSONL output file (default: meeting_<timestamp>.jsonl)",
)
@click.option(
    "--snapshot-interval",
    default=120.0,
    type=float,
    help="Seconds between full-state snapshots (default: 120)",
)
@click.option(
    "--speaker-debounce",
    default=3,
    type=int,
    help="Consecutive polls before confirming a speaker (default: 3)",
)
def track(
    port: int,
    interval: float,
    output: str | None,
    snapshot_interval: float,
    speaker_debounce: int,
):
    """Track a live Teams meeting: participants, speakers, events.

    Polls the Teams tab via Chrome DevTools and logs changes to JSONL.
    Requires Chrome running with --remote-debugging-port.
    """
    if output is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = f"meeting_{ts}.jsonl"

    tracker = TeamsTracker(
        debug_port=port,
        output_path=output,
        speaker_debounce=speaker_debounce,
    )
    console.print(
        f"[bold]Teams Meeting Tracker[/bold]  "
        f"(poll every {interval}s, "
        f"snapshots every {snapshot_interval:.0f}s → {output})"
    )
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    def on_event(event: dict) -> None:
        etype = event.get("type", "")
        name = event.get("name", event.get("email", ""))
        icons = {
            "join": "[green]+[/green]",
            "leave": "[red]-[/red]",
            "speaker_start": "[bold green]\u266b[/bold green]",
            "speaker_stop": "[dim]\u266b[/dim]",
            "mute": "[yellow]\U0001f507[/yellow]",
            "unmute": "[green]\U0001f50a[/green]",
            "screen_share_start": "[cyan]\U0001f4bb[/cyan]",
            "screen_share_stop": "[dim]\U0001f4bb[/dim]",
        }
        icon = icons.get(etype, "\u2022")
        ts = event.get("ts", "")
        # Show only time portion
        time_str = ts.split("T")[1][:8] if "T" in ts else ts
        console.print(f"  {time_str}  {icon} {etype:<20} {name}")

    def on_snapshot(snapshot) -> None:
        names = [p.name for p in snapshot.participants]
        speakers = [
            snapshot.participants[i].name
            for i, email in enumerate(
                p.email for p in snapshot.participants
            )
            if email in snapshot.speakers
        ]
        console.print(
            f"\n[dim]--- snapshot "
            f"({snapshot.call_duration}) "
            f"| {len(names)} participants"
            f"{' | speaking: ' + ', '.join(speakers) if speakers else ''}"
            f" ---[/dim]\n"
        )

    try:
        asyncio.run(
            tracker.run(
                interval=interval,
                snapshot_interval=snapshot_interval,
                on_event=on_event,
                on_snapshot=on_snapshot,
            )
        )
    except KeyboardInterrupt:
        console.print(f"\n[bold]Stopped.[/bold] Events saved to {output}")


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
