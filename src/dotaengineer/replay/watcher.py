"""File system watcher for Dota 2 replay directory.

Watches for new .dem files and triggers parsing + match creation.
"""

from __future__ import annotations

import time
from pathlib import Path

import structlog
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from dotaengineer.config import settings

log = structlog.get_logger()


class ReplayHandler(FileSystemEventHandler):
    """Handle new .dem files in the replay directory."""

    def __init__(self, on_new_replay):
        self._on_new_replay = on_new_replay
        self._processed: set[str] = set()

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix != ".dem":
            return
        if str(path) in self._processed:
            return

        # Wait for file to finish writing
        log.info("replay_detected", path=str(path))
        time.sleep(5)

        self._processed.add(str(path))
        self._on_new_replay(path)


def start_watcher(
    watch_dir: str | None = None,
    on_new_replay=None,
) -> Observer | None:
    """Start watching a directory for new .dem replay files.

    Args:
        watch_dir: Directory to watch. Defaults to settings.replay_watch_dir.
        on_new_replay: Callback function that receives a Path to the new .dem file.
                       Defaults to parse_and_create_match.

    Returns:
        The Observer instance, or None if watch_dir is not configured.
    """
    directory = watch_dir or settings.replay_watch_dir
    if not directory:
        log.info("replay_watcher_disabled", reason="no replay_watch_dir configured")
        return None

    dir_path = Path(directory)
    if not dir_path.exists():
        log.warning("replay_watch_dir_not_found", path=directory)
        return None

    if on_new_replay is None:
        on_new_replay = _default_handler

    handler = ReplayHandler(on_new_replay)
    observer = Observer()
    observer.schedule(handler, str(dir_path), recursive=False)
    observer.start()
    log.info("replay_watcher_started", path=directory)
    return observer


def _default_handler(replay_path: Path) -> None:
    """Default handler: parse replay and create match in the database."""
    from dotaengineer.db import get_connection
    from dotaengineer.replay.parser import parse_replay_to_match
    from dotaengineer.services.match_service import create_match

    result = parse_replay_to_match(replay_path)
    if result is None:
        log.warning(
            "replay_parse_returned_none",
            path=str(replay_path),
            hint="Use manual entry at /matches/new",
        )
        return

    result.source = "replay"
    result.replay_file = str(replay_path)

    con = get_connection()
    try:
        match_id = create_match(result, con)
        log.info("match_created_from_replay", match_id=match_id, path=str(replay_path))
    finally:
        con.close()


def stop_watcher(observer: Observer) -> None:
    """Stop the replay file watcher."""
    observer.stop()
    observer.join()
    log.info("replay_watcher_stopped")
