"""Parse Dota 2 .dem replay files to extract match data.

Two-layer approach:
1. Java clarity parser (full stats: KDA, GPM, damage, items, net worth)
   → requires one-time setup: `dotaengineer setup-parser`
2. Pure Python CDemoFileInfo reader (basic: heroes, teams, winner, duration)
   → always works, no extra dependencies

The parser tries Java first, falls back to Python.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import structlog

from dotaengineer.models.hero import get_all_heroes
from dotaengineer.models.match import MatchCreate, MatchPlayerCreate

log = structlog.get_logger()

# Default location for the clarity-based parser JAR
_PARSER_JAR_NAME = "dotacafe-parser.jar"


def _find_parser_jar() -> Path | None:
    """Locate the Java parser JAR file."""
    candidates = [
        Path("data") / _PARSER_JAR_NAME,
        Path("tools/replay-parser/target") / _PARSER_JAR_NAME,
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _java_available() -> bool:
    """Check if Java is installed."""
    return shutil.which("java") is not None


def parse_replay(replay_path: str | Path) -> MatchCreate | None:
    """Parse a .dem replay file. Tries Java parser first, falls back to Python.

    Returns a MatchCreate model ready for match_service.create_match(),
    or None if parsing fails entirely.
    """
    path = Path(replay_path)
    if not path.exists() or path.suffix != ".dem":
        log.warning("replay_file_invalid", path=str(path))
        return None

    # Try 1: Java clarity parser (full stats)
    jar = _find_parser_jar()
    if jar and _java_available():
        result = _parse_with_java(path, jar)
        if result:
            return result
        log.warning("java_parser_failed_falling_back", path=str(path))

    # Try 2: Pure Python CDemoFileInfo parser (basic data)
    result = _parse_with_python(path)
    if result:
        log.info(
            "replay_parsed_basic",
            path=str(path),
            hint="Setup Java parser for full stats: dotaengineer setup-parser",
        )
        return result

    log.error("replay_parse_failed", path=str(path))
    return None


# Alias for backwards compatibility
parse_replay_to_match = parse_replay


# ── Java clarity parser ──────────────────────────────────────────────────────


def _parse_with_java(path: Path, jar: Path) -> MatchCreate | None:
    """Parse replay using the clarity-based Java parser (full stats)."""
    try:
        result = subprocess.run(
            ["java", "-jar", str(jar), str(path)],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            log.error("java_parser_error", stderr=result.stderr[:500])
            return None

        data = json.loads(result.stdout)
        return _java_json_to_match(data, path)

    except subprocess.TimeoutExpired:
        log.error("java_parser_timeout", path=str(path))
        return None
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        log.error("java_parser_output_error", error=str(e))
        return None
    except FileNotFoundError:
        log.warning("java_not_found")
        return None


def _java_json_to_match(data: dict, replay_path: Path) -> MatchCreate:
    """Map Java parser JSON output to MatchCreate model."""
    radiant_win = data.get("radiant_win", True)
    duration = data.get("duration", 0)
    game_mode = _game_mode_name(data.get("game_mode", 0))

    players = []
    for p in data.get("players", []):
        slot = p.get("slot", 0)
        team = p.get("team", "radiant" if slot < 5 else "dire")

        hero_name = p.get("hero_name", "")
        # LAN replays: Java parser returns hero_name_id (int) directly
        hero_id = p.get("hero_name_id", 0) or _resolve_hero_id(hero_name)

        players.append(
            MatchPlayerCreate(
                slot=slot,
                hero_id=hero_id,
                team=team,
                kills=p.get("kills", 0),
                deaths=p.get("deaths", 0),
                assists=p.get("assists", 0),
                last_hits=p.get("last_hits", 0),
                denies=p.get("denies", 0),
                gpm=p.get("gpm", 0),
                xpm=p.get("xpm", 0),
                net_worth=p.get("net_worth", 0),
                hero_damage=p.get("hero_damage", 0),
                tower_damage=p.get("tower_damage", 0),
                hero_healing=p.get("hero_healing", 0),
                level=p.get("level", 0),
            )
        )

    return MatchCreate(
        played_at=datetime.now(),
        duration_seconds=duration,
        radiant_win=radiant_win,
        game_mode=game_mode,
        radiant_score=data.get("radiant_score", 0),
        dire_score=data.get("dire_score", 0),
        players=players,
        source="replay",
        replay_file=str(replay_path),
    )


# ── Pure Python parser (CDemoFileInfo only) ──────────────────────────────────


def _parse_with_python(path: Path) -> MatchCreate | None:
    """Parse replay using pure Python CDemoFileInfo reader (basic data only).

    Gets: heroes, teams, winner, duration.
    Does NOT get: KDA, GPM, damage, items (all set to 0).
    """
    from dotaengineer.replay.dem_reader import read_demo_file_info

    try:
        info = read_demo_file_info(path)
    except Exception as e:
        log.error("python_parser_error", path=str(path), error=str(e))
        return None

    if info is None:
        return None

    # Filter out fake clients (bots/spectators with no hero)
    real_players = [p for p in info.players if not p.is_fake_client and p.hero_name]

    if len(real_players) < 2:
        log.warning("too_few_players_in_replay", count=len(real_players))
        return None

    radiant_win = info.game_winner == 2  # 2=Radiant, 3=Dire

    players = []
    for i, p in enumerate(real_players[:10]):
        team = "radiant" if p.game_team == 2 else "dire"
        hero_id = _resolve_hero_id(p.hero_name)

        players.append(
            MatchPlayerCreate(
                slot=i,
                hero_id=hero_id,
                team=team,
                # Stats are 0 — only available via Java parser
            )
        )

    game_mode = _game_mode_name(info.game_mode)

    return MatchCreate(
        played_at=datetime.now(),
        duration_seconds=int(info.playback_time) if info.playback_time > 0 else None,
        radiant_win=radiant_win,
        game_mode=game_mode,
        players=players,
        source="replay",
        replay_file=str(path),
    )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _resolve_hero_id(hero_name: str) -> int:
    """Resolve hero internal name (e.g. 'npc_dota_hero_invoker') to hero ID."""
    if not hero_name:
        return 0

    for h in get_all_heroes():
        if h.name == hero_name:
            return h.id

    # Try partial match (without prefix)
    short = hero_name.replace("npc_dota_hero_", "")
    for h in get_all_heroes():
        h_short = h.name.replace("npc_dota_hero_", "")
        if h_short == short:
            return h.id

    log.warning("hero_not_found", hero_name=hero_name)
    return 0


def _game_mode_name(mode_id: int) -> str:
    """Convert Dota 2 game mode ID to string."""
    modes = {
        0: "unknown",
        1: "all_pick",
        2: "captains_mode",
        3: "random_draft",
        4: "single_draft",
        5: "all_random",
        11: "mid_only",
        12: "least_played",
        16: "captains_draft",
        18: "ability_draft",
        22: "all_pick_ranked",
        23: "turbo",
    }
    return modes.get(mode_id, f"mode_{mode_id}")
