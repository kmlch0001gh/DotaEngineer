"""CLI entry point — dotaengineer <command>.

Usage:
  dotaengineer ingest meta          # run meta ingestion pipeline
  dotaengineer ingest player        # run personal match history pipeline
  dotaengineer analyze counters     # print counter-picks for enemy heroes
  dotaengineer analyze performance  # print personal performance report
  dotaengineer serve api            # start FastAPI server
  dotaengineer serve dashboard      # start Streamlit dashboard
"""

from __future__ import annotations

import asyncio
import subprocess

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="dotaengineer", help="High-MMR Dota 2 data platform.")
ingest = typer.Typer(help="Data ingestion pipelines.")
analyze = typer.Typer(help="Analysis commands.")
serve = typer.Typer(help="Start servers.")

app.add_typer(ingest, name="ingest")
app.add_typer(analyze, name="analyze")
app.add_typer(serve, name="serve")

console = Console()


@ingest.command("meta")
def ingest_meta():
    """Ingest high-MMR hero meta from OpenDota and Stratz."""
    from dotaengineer.pipelines.meta_pipeline import meta_ingestion_flow

    console.print("[bold green]Starting meta ingestion pipeline...[/]")
    asyncio.run(meta_ingestion_flow())
    console.print("[bold green]Done.[/]")


@ingest.command("player")
def ingest_player(
    account_id: int = typer.Option(0, help="Steam account ID (32-bit). Uses MY_STEAM_ID if not set."),
    limit: int = typer.Option(200, help="Number of recent matches to fetch."),
):
    """Ingest personal match history."""
    from dotaengineer.pipelines.player_pipeline import player_ingestion_flow

    console.print(f"[bold green]Starting player ingestion (last {limit} matches)...[/]")
    asyncio.run(player_ingestion_flow(account_id=account_id or None, limit=limit))
    console.print("[bold green]Done.[/]")


@analyze.command("counters")
def analyze_counters(
    enemies: str = typer.Argument(..., help="Comma-separated enemy hero IDs, e.g. '1,2,3'"),
    allies: str = typer.Option("", help="Comma-separated allied hero IDs"),
    pool: str = typer.Option("", help="Comma-separated hero pool IDs to restrict picks"),
    top: int = typer.Option(10, help="Number of results"),
):
    """Get best picks vs an enemy lineup."""
    from dotaengineer.analysis.draft import DraftAnalyzer

    enemy_ids = [int(x.strip()) for x in enemies.split(",") if x.strip()]
    ally_ids = [int(x.strip()) for x in allies.split(",") if x.strip()]
    pool_ids = [int(x.strip()) for x in pool.split(",") if x.strip()] or None

    analyzer = DraftAnalyzer()
    df = analyzer.get_best_pick(ally_ids, enemy_ids, pool=pool_ids, top_n=top)

    table = Table(title="Best Picks vs Enemy Draft")
    for col in df.columns:
        table.add_column(col)
    for row in df.iter_rows():
        table.add_row(*[str(v) for v in row])

    console.print(table)


@analyze.command("performance")
def analyze_performance(
    account_id: int = typer.Option(0, help="Steam account ID. Uses MY_STEAM_ID if not set."),
):
    """Print personal performance report."""
    from dotaengineer.analysis.player_performance import PlayerPerformanceAnalyzer

    analyzer = PlayerPerformanceAnalyzer(account_id or None)

    console.print("\n[bold]Hero Pool — Worst Heroes vs Meta:[/]")
    worst = analyzer.worst_heroes()
    t = Table()
    for col in worst.columns:
        t.add_column(col)
    for row in worst.iter_rows():
        t.add_row(*[str(v) for v in row])
    console.print(t)

    console.print("\n[bold]Duration Split Win Rates:[/]")
    splits = analyzer.win_loss_by_duration()
    t2 = Table()
    for col in splits.columns:
        t2.add_column(col)
    for row in splits.iter_rows():
        t2.add_row(*[str(v) for v in row])
    console.print(t2)


@analyze.command("meta")
def analyze_meta():
    """Print current meta tier list at immortal bracket."""
    from dotaengineer.analysis.meta import MetaAnalyzer

    analyzer = MetaAnalyzer()
    df = analyzer.tier_list()

    table = Table(title="Immortal Meta Tier List")
    for col in df.columns:
        table.add_column(col)
    for row in df.iter_rows():
        table.add_row(*[str(v) for v in row])
    console.print(table)


@serve.command("api")
def serve_api(
    host: str = typer.Option("0.0.0.0"),
    port: int = typer.Option(8000),
    reload: bool = typer.Option(False),
):
    """Start the FastAPI server."""
    import uvicorn

    uvicorn.run(
        "dotaengineer.api.routes:app",
        host=host,
        port=port,
        reload=reload,
    )


@serve.command("dashboard")
def serve_dashboard():
    """Start the Streamlit dashboard."""
    subprocess.run(
        ["streamlit", "run", "src/dotaengineer/dashboard/app.py"],
        check=True,
    )
