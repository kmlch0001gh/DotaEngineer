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

    # Collect existing replay filenames (not full paths) to avoid duplicates
    existing_names = set()
    for (rf,) in con.execute("SELECT replay_file FROM matches").fetchall():
        if rf:
            existing_names.add(Path(rf).name)

    dems = sorted(directory.glob("*.dem"))
    new_count = 0

    for path in dems:
        if path.name in existing_names:
            console.print(f"[dim]SKIP {path.name}[/]")
            continue

        console.print(f"[bold]PARSING {path.name}...[/]")
        # Resolve to absolute path for consistent storage
        result = parse_replay(path.resolve())
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
    console.print(f"\n[bold green]{new_count} new, {len(existing_names)} skipped.[/]")


@app.command("parse")
def parse_replay_cmd(
    replay_file: str = typer.Argument(..., help="Path to .dem replay file"),
):
    """Parse a single .dem replay and create a match in the database."""
    from rich.table import Table

    from dotaengineer.db import get_connection
    from dotaengineer.replay.parser import parse_replay
    from dotaengineer.services.match_service import create_match

    path = Path(replay_file).resolve()
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


@app.command("backfill-achievements")
def backfill_achievements_cmd(
    replay_dir: str = typer.Argument("data/replays", help="Directory with .dem replay files"),
):
    """Backfill multi-kills, kill streaks, courier/tormentor kills for existing matches.

    Reparses each replay file, finds the matching match in the DB by replay_file,
    and updates only the achievement columns. Does NOT modify KDA, items, claims, or ELO.
    Safe to run multiple times — overwrites achievement columns with fresh data.
    """
    from dotaengineer.db import get_connection, release_connection
    from dotaengineer.replay.parser import parse_replay

    replay_path = Path(replay_dir)
    if not replay_path.exists():
        console.print(f"[bold red]Directory not found: {replay_path}[/]")
        raise typer.Exit(1)

    files = sorted(replay_path.glob("*.dem"))
    if not files:
        console.print("[bold red]No .dem files found.[/]")
        raise typer.Exit(1)

    console.print(f"[bold]Scanning {len(files)} replays for achievements...[/]")

    con = get_connection()
    updated = 0
    for f in files:
        result = parse_replay(f.resolve())
        if not result:
            continue

        # Find match by replay_file name (compare filenames only)
        rows = con.execute(
            "SELECT id, replay_file FROM matches WHERE replay_file IS NOT NULL",
        ).fetchall()

        match_id = None
        for row in rows:
            if row[1] and Path(row[1]).name == f.name:
                match_id = row[0]
                break

        if not match_id:
            console.print(f"  [dim]{f.name}: no matching match in DB[/]")
            continue

        # Update each slot's achievement columns
        match_updated = False
        for p in result.players:
            has_data = (
                p.double_kills or p.triple_kills or p.ultra_kills or p.rampage
                or p.killing_sprees or p.dominating or p.mega_kills
                or p.unstoppable or p.wicked_sick or p.monster_kill
                or p.godlike or p.beyond_godlike
                or p.courier_kills or p.tormentor_kills
            )
            con.execute(
                """UPDATE match_players SET
                    double_kills = ?, triple_kills = ?, ultra_kills = ?, rampage = ?,
                    killing_sprees = ?, dominating = ?, mega_kills = ?,
                    unstoppable = ?, wicked_sick = ?, monster_kill = ?,
                    godlike = ?, beyond_godlike = ?,
                    courier_kills = ?, tormentor_kills = ?
                WHERE match_id = ? AND slot = ?""",
                [
                    p.double_kills, p.triple_kills, p.ultra_kills, p.rampage,
                    p.killing_sprees, p.dominating, p.mega_kills,
                    p.unstoppable, p.wicked_sick, p.monster_kill,
                    p.godlike, p.beyond_godlike,
                    p.courier_kills, p.tormentor_kills,
                    match_id, p.slot,
                ],
            )
            if has_data:
                match_updated = True

        if match_updated:
            console.print(f"  {f.name} → Match #{match_id}: achievements updated")
            updated += 1
        else:
            console.print(f"  [dim]{f.name} → Match #{match_id}: no achievements found[/]")

    release_connection(con)
    console.print(f"[bold green]Done. {updated} matches updated.[/]")


@app.command("sync-data")
def sync_data(
    job: str = typer.Option(
        "", help="Job: hero-meta, item-builds, pro-players, pro-matches"
    ),
):
    """Sync public Dota 2 data from OpenDota API.

    Runs all jobs by default, or a specific one with --job.
    """
    from dotaengineer.db import get_connection, release_connection
    from dotaengineer.pipeline.sources.opendota import OpenDotaClient

    con = get_connection()
    client = OpenDotaClient()

    try:
        if job == "hero-meta" or not job:
            from dotaengineer.pipeline.jobs.hero_meta import sync_hero_meta
            n = sync_hero_meta(con, client)
            console.print(f"[green]Hero meta: {n} rows synced[/]")

        if job == "hero-counters" or not job:
            from dotaengineer.pipeline.jobs.hero_meta import sync_hero_counters
            n = sync_hero_counters(con, client)
            console.print(f"[green]Hero counters: {n} rows synced[/]")

        if job == "item-builds" or not job:
            from dotaengineer.pipeline.jobs.item_builds import sync_item_builds
            n = sync_item_builds(con, client)
            console.print(f"[green]Item builds: {n} rows synced[/]")

        if job == "pro-players" or not job:
            from dotaengineer.pipeline.jobs.pro_players import sync_pro_players
            n = sync_pro_players(con, client)
            console.print(f"[green]Pro players: {n} tracked[/]")

        if job == "pro-matches" or not job:
            from dotaengineer.pipeline.jobs.pro_matches import sync_pro_matches
            n = sync_pro_matches(con, client)
            console.print(f"[green]Pro matches: {n} synced[/]")

        if job == "player-matches":
            from dotaengineer.pipeline.jobs.pro_matches import sync_tracked_player_matches
            n = sync_tracked_player_matches(con, client)
            console.print(f"[green]Player matches: {n} synced[/]")

        console.print("[bold green]Sync complete.[/]")
    finally:
        client.close()
        release_connection(con)


@app.command("track-player")
def track_player(
    account_id: int = typer.Argument(..., help="Steam account ID"),
    name: str = typer.Option("", help="Player name"),
    category: str = typer.Option("high_mmr", help="Category: pro or high_mmr"),
    team: str = typer.Option("", help="Team name"),
):
    """Add a player to the tracking list."""
    from dotaengineer.db import get_connection, release_connection
    from dotaengineer.pipeline.jobs.pro_players import add_tracked_player

    if not name:
        name = f"Player_{account_id}"

    con = get_connection()
    add_tracked_player(con, account_id, name, category, team)
    release_connection(con)
    console.print(f"[green]Tracking {name} (ID: {account_id}, {category})[/]")


@app.command("tracked-players")
def list_tracked_players():
    """List all tracked pro/high-MMR players."""
    from rich.table import Table

    from dotaengineer.db import get_connection, release_connection

    con = get_connection()
    rows = con.execute(
        "SELECT account_id, name, team, category, region, synced_at "
        "FROM dota_tracked_players ORDER BY category, name"
    ).fetchall()
    release_connection(con)

    table = Table(title="Tracked Players")
    table.add_column("Account ID")
    table.add_column("Name")
    table.add_column("Team")
    table.add_column("Category")
    table.add_column("Region")
    table.add_column("Last Sync")

    for r in rows:
        table.add_row(
            str(r[0]), r[1], r[2] or "", r[3], r[4] or "",
            r[5].strftime("%Y-%m-%d %H:%M") if r[5] else "—",
        )

    console.print(table)
    console.print(f"[dim]{len(rows)} players tracked[/]")


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
