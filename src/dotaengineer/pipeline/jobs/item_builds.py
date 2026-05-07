"""Sync popular item builds per hero from OpenDota."""

from __future__ import annotations

import json

import structlog

from dotaengineer.db import Connection
from dotaengineer.pipeline.sources.opendota import OpenDotaClient

log = structlog.get_logger()

# Map OpenDota phase keys to our build_type
PHASES = {
    "start_game_items": "start",
    "early_game_items": "early",
    "mid_game_items": "core",
    "late_game_items": "late",
}


def sync_item_builds(
    con: Connection, client: OpenDotaClient, item_names: dict | None = None
) -> int:
    """Sync popular item builds for all heroes.

    Fetches /heroes/{id}/itemPopularity for each hero (~130 calls).
    Stores top items per phase with pick count.

    Args:
        item_names: {item_id_str: item_name} mapping. If None, fetches from API.

    Returns number of build rows upserted.
    """
    log.info("sync_item_builds_start")

    # Get item name mapping if not provided
    if item_names is None:
        try:
            items_data = client.constants("items")
            item_names = {}
            for name, data in items_data.items():
                if isinstance(data, dict) and "id" in data:
                    item_names[str(data["id"])] = name
        except Exception:
            item_names = {}

    # Get hero list
    heroes = con.execute(
        "SELECT DISTINCT hero_id, hero_name FROM dota_hero_meta"
    ).fetchall()
    if not heroes:
        hero_data = client.hero_stats()
        heroes = [(h["id"], h.get("localized_name", "")) for h in hero_data]

    count = 0
    for hero_id, hero_name in heroes:
        try:
            data = client.hero_item_popularity(hero_id)
        except Exception as e:
            log.warning(
                "item_popularity_failed", hero_id=hero_id, error=str(e)
            )
            continue

        if not data or not isinstance(data, dict):
            continue

        for phase_key, build_type in PHASES.items():
            phase_data = data.get(phase_key)
            if not phase_data or not isinstance(phase_data, dict):
                continue

            # Sort by count, take top 10
            items = []
            for item_id_str, pick_count in sorted(
                phase_data.items(), key=lambda x: x[1], reverse=True
            )[:10]:
                name = item_names.get(item_id_str, f"item_{item_id_str}")
                items.append({
                    "item_id": int(item_id_str),
                    "item_name": name,
                    "count": pick_count,
                })

            if not items:
                continue

            con.execute(
                """
                INSERT INTO dota_hero_builds
                    (hero_id, hero_name, bracket, build_type, items, synced_at)
                VALUES (?, ?, 'all', ?, ?::jsonb, now())
                ON CONFLICT (hero_id, bracket, build_type)
                DO UPDATE SET
                    hero_name = ?, items = ?::jsonb, synced_at = now()
                """,
                [
                    hero_id, hero_name, build_type, json.dumps(items),
                    hero_name, json.dumps(items),
                ],
            )
            count += 1

    log.info("sync_item_builds_done", rows=count)
    return count
