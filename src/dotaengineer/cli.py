"""CLI entry point — dotaengineer <command>.

Usage:
  dotaengineer serve                  # start web server on :8000
  dotaengineer init-db                # create database schema
  dotaengineer add-player USERNAME    # quick player registration
  dotaengineer recalc-elo             # recalculate all ELO from scratch
  dotaengineer backup                 # backup database file
  dotaengineer fetch-heroes           # download hero data (needs internet)
  dotaengineer setup-parser           # build Java replay parser (needs Java + Maven)
  dotaengineer watch --dir PATH       # watch for new .dem replays
  dotaengineer parse FILE.dem         # parse a single replay file
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(name="dotaengineer", help="Dota 2 cybercafe stats tracker.")
console = Console()


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind host"),
    port: int = typer.Option(8000, help="Bind port"),
    reload: bool = typer.Option(False, help="Enable auto-reload"),
):
    """Start the web server."""
    import uvicorn

    console.print(f"[bold green]Starting {host}:{port}...[/]")
    uvicorn.run(
        "dotaengineer.api.app:app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command("init-db")
def init_db():
    """Initialize the database schema."""
    from dotaengineer.db import init_schema

    init_schema()
    console.print("[bold green]Database schema initialized.[/]")


@app.command("add-player")
def add_player(
    username: str = typer.Argument(..., help="Player username"),
    display_name: str = typer.Option("", help="Display name (defaults to username)"),
    pin: str = typer.Option("", help="4-digit PIN"),
):
    """Quick player registration from the CLI."""
    from dotaengineer.db import get_connection
    from dotaengineer.models.player import PlayerCreate
    from dotaengineer.services.player_service import create_player

    display = display_name or username
    data = PlayerCreate(
        username=username,
        display_name=display,
        pin=pin if pin else None,
    )
    con = get_connection()
    try:
        player_id = create_player(data, con)
        console.print(f"[bold green]Player '{display}' created (ID {player_id}).[/]")
    finally:
        con.close()


@app.command("recalc-elo")
def recalc_elo():
    """Recalculate all ELO ratings from match history."""
    from dotaengineer.db import get_connection
    from dotaengineer.elo import recalculate_all

    con = get_connection()
    try:
        count = recalculate_all(con)
        console.print(f"[bold green]ELO recalculated: {count} matches processed.[/]")
    finally:
        con.close()


@app.command()
def backup():
    """Backup the database to a timestamped file."""
    from dotaengineer.config import settings

    src = Path(settings.duckdb_path)
    if not src.exists():
        console.print("[bold red]Database file not found.[/]")
        raise typer.Exit(1)

    backup_dir = src.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = backup_dir / f"cafe_{timestamp}.duckdb"
    shutil.copy2(src, dst)
    console.print(f"[bold green]Backup saved: {dst}[/]")


@app.command("fetch-heroes")
def fetch_heroes():
    """Download hero data from OpenDota API (requires internet)."""
    import asyncio
    import json

    import httpx

    from dotaengineer.config import settings

    async def _fetch():
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://api.opendota.com/api/heroes")
            resp.raise_for_status()
            return resp.json()

    console.print("[bold]Fetching hero data from OpenDota...[/]")
    heroes_raw = asyncio.run(_fetch())

    heroes = []
    for h in heroes_raw:
        name = h["name"].replace("npc_dota_hero_", "")
        heroes.append(
            {
                "id": h["id"],
                "name": h["name"],
                "localized_name": h["localized_name"],
                "primary_attr": h.get("primary_attr", "all"),
                "attack_type": h.get("attack_type", "Melee"),
                "roles": h.get("roles", []),
                "img": f"/static/hero_icons/{name}.png",
            }
        )

    heroes.sort(key=lambda x: x["id"])
    path = settings.heroes_json_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(heroes, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"[bold green]{len(heroes)} heroes saved to {path}[/]")


# ── Replay commands ──────────────────────────────────────────────────────────


@app.command("setup-parser")
def setup_parser():
    """Build the Java replay parser (requires Java 17+ and Maven).

    This compiles the clarity-based parser that extracts full match stats
    (KDA, GPM, damage, items) from .dem replay files.

    One-time setup — after this, `dotaengineer parse` and `dotaengineer watch`
    will automatically use the Java parser for complete data.
    """
    tools_dir = Path("tools/replay-parser")
    pom = tools_dir / "pom.xml"

    if not pom.exists():
        console.print("[bold red]tools/replay-parser/pom.xml not found.[/]")
        console.print("Make sure you're in the project root directory.")
        raise typer.Exit(1)

    # Check prerequisites
    if not shutil.which("java"):
        console.print("[bold red]Java not found.[/]")
        console.print("Install Java 17+: https://adoptium.net/")
        raise typer.Exit(1)

    if not shutil.which("mvn"):
        console.print("[bold red]Maven not found.[/]")
        console.print("Install Maven: https://maven.apache.org/install.html")
        raise typer.Exit(1)

    console.print("[bold]Building replay parser with Maven...[/]")
    console.print("(first build downloads dependencies, may take a minute)")

    result = subprocess.run(
        ["mvn", "package", "-q", "-DskipTests"],
        cwd=str(tools_dir),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        console.print(f"[bold red]Build failed:[/]\n{result.stderr[:1000]}")
        raise typer.Exit(1)

    jar_src = tools_dir / "target" / "dotacafe-parser.jar"
    if not jar_src.exists():
        console.print("[bold red]JAR not found after build.[/]")
        raise typer.Exit(1)

    # Copy JAR to data/ for easy access
    jar_dst = Path("data") / "dotacafe-parser.jar"
    jar_dst.parent.mkdir(exist_ok=True)
    shutil.copy2(jar_src, jar_dst)

    console.print(f"[bold green]Parser built: {jar_dst}[/]")
    console.print("Replay parsing will now include full stats (KDA, GPM, damage).")


@app.command("parse-new")
def parse_new_replays(
    replay_dir: str = typer.Argument("data/replays", help="Directory with .dem replay files"),
):
    """Parse only NEW replays that aren't already in the database."""
    from dotaengineer.db import get_connection, release_connection
    from dotaengineer.replay.parser import parse_replay
    from dotaengineer.services.match_service import create_match, get_match

    directory = Path(replay_dir)
    if not directory.exists():
        console.print(f"[bold red]Directory not found: {directory}[/]")
        raise typer.Exit(1)

    con = get_connection()
    existing = set()
    for (rf,) in con.execute("SELECT replay_file FROM matches").fetchall():
        if rf:
            existing.add(rf)

    dems = sorted(directory.glob("*.dem"))
    new_count = 0

    for path in dems:
        if str(path) in existing:
            console.print(f"[dim]SKIP {path.name}[/]")
            continue

        console.print(f"[bold]PARSING {path.name}...[/]")
        result = parse_replay(path)
        if not result:
            console.print("  [red]FAILED[/]")
            continue

        mid = create_match(result, con)
        m = get_match(mid, con)
        w = "Radiant" if m.radiant_win else "Dire"
        console.print(
            f"  [green]Match #{mid}[/] — {w} Win "
            f"{m.radiant_score}-{m.dire_score} — {m.duration_display}"
        )
        new_count += 1

    release_connection(con)
    console.print(f"\n[bold green]{new_count} new, {len(existing)} skipped.[/]")


@app.command("parse")
def parse_replay_cmd(
    replay_file: str = typer.Argument(..., help="Path to .dem replay file"),
):
    """Parse a single .dem replay and create a match in the database."""
    from rich.table import Table

    from dotaengineer.db import get_connection
    from dotaengineer.replay.parser import parse_replay
    from dotaengineer.services.match_service import create_match

    path = Path(replay_file)
    if not path.exists():
        console.print(f"[bold red]File not found: {path}[/]")
        raise typer.Exit(1)

    console.print(f"[bold]Parsing {path.name}...[/]")
    match_data = parse_replay(path)

    if match_data is None:
        console.print("[bold red]Could not parse replay.[/]")
        raise typer.Exit(1)

    # Show parsed data
    console.print(
        f"  Winner: [{'green' if match_data.radiant_win else 'red'}]"
        f"{'Radiant' if match_data.radiant_win else 'Dire'}[/]"
    )
    if match_data.duration_seconds:
        m, s = divmod(match_data.duration_seconds, 60)
        console.print(f"  Duration: {m}:{s:02d}")
    console.print(f"  Players: {len(match_data.players)}")
    console.print(f"  Source: {match_data.source}")

    table = Table(title="Players")
    table.add_column("Slot")
    table.add_column("Team")
    table.add_column("Hero ID")
    table.add_column("K/D/A")
    table.add_column("GPM")
    for p in match_data.players:
        kda = f"{p.kills}/{p.deaths}/{p.assists}"
        has_stats = p.kills > 0 or p.deaths > 0 or p.assists > 0
        table.add_row(
            str(p.slot),
            p.team,
            str(p.hero_id),
            kda if has_stats else "[dim]—[/]",
            str(p.gpm) if p.gpm > 0 else "[dim]—[/]",
        )
    console.print(table)

    # Save to database
    con = get_connection()
    try:
        match_id = create_match(match_data, con)
        console.print(f"[bold green]Match #{match_id} created from replay.[/]")
    finally:
        con.close()


@app.command("backfill-bans")
def backfill_bans_cmd(
    replay_dir: str = typer.Argument("data/replays", help="Directory with .dem replay files"),
):
    """Add bans to existing matches that were parsed before ban tracking.

    Parses each replay, finds the matching match by replay_file path,
    and inserts bans if the match doesn't have them yet.
    Safe to run multiple times — skips matches that already have bans.
    Does NOT modify players, claims, or ELO.
    """
    from dotaengineer.db import get_connection, release_connection
    from dotaengineer.replay.parser import parse_replay
    from dotaengineer.services.match_service import backfill_bans

    replay_path = Path(replay_dir)
    if not replay_path.exists():
        console.print(f"[bold red]Directory not found: {replay_path}[/]")
        raise typer.Exit(1)

    files = sorted(replay_path.glob("*.dem"))
    if not files:
        console.print("[bold red]No .dem files found.[/]")
        raise typer.Exit(1)

    console.print(f"[bold]Scanning {len(files)} replays for bans...[/]")

    con = get_connection()
    total = 0
    for f in files:
        result = parse_replay(f)
        if not result or not result.bans:
            continue

        # Find match by replay_file path
        row = con.execute(
            "SELECT id FROM matches WHERE replay_file = ?",
            [str(f)],
        ).fetchone()

        if not row:
            console.print(f"  [dim]{f.name}: no matching match in DB[/]")
            continue

        match_id = row[0]
        inserted = backfill_bans(match_id, result.bans, con)
        if inserted > 0:
            console.print(f"  {f.name} → Match #{match_id}: {inserted} bans added")
            total += inserted
        else:
            console.print(f"  [dim]{f.name} → Match #{match_id}: already has bans[/]")

    release_connection(con)
    console.print(f"[bold green]Done. {total} bans added total.[/]")


@app.command("watch")
def watch_replays(
    dir: str = typer.Option("", help="Replay directory to watch"),
):
    """Watch a directory for new .dem replays and auto-create matches.

    If --dir is not provided, uses REPLAY_WATCH_DIR from .env config.
    """
    from dotaengineer.replay.watcher import start_watcher, stop_watcher

    watch_dir = dir or None
    observer = start_watcher(watch_dir=watch_dir)

    if observer is None:
        console.print("[bold red]Watcher not started.[/]")
        console.print("Set REPLAY_WATCH_DIR in .env or use --dir")
        raise typer.Exit(1)

    console.print("[bold green]Watching for new .dem replays...[/]")
    console.print("Press Ctrl+C to stop.")

    try:
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_watcher(observer)
        console.print("\n[bold]Watcher stopped.[/]")
