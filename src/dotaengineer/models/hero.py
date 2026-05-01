"""Hero data model and static hero data loader."""

from __future__ import annotations

import json
from functools import lru_cache

from pydantic import BaseModel

from dotaengineer.config import settings


class Hero(BaseModel):
    id: int
    name: str  # internal name, e.g. "npc_dota_hero_antimage"
    localized_name: str  # display name, e.g. "Anti-Mage"
    primary_attr: str  # "str", "agi", "int", "all"
    attack_type: str  # "Melee", "Ranged"
    roles: list[str]
    img: str  # hero portrait URL
    icon: str = ""  # small icon URL


@lru_cache(maxsize=1)
def _load_heroes() -> list[Hero]:
    path = settings.heroes_json_path
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Hero(**h) for h in data]


def get_all_heroes() -> list[Hero]:
    return _load_heroes()


def get_hero_by_id(hero_id: int) -> Hero | None:
    for h in _load_heroes():
        if h.id == hero_id:
            return h
    return None


def get_hero_name(hero_id: int) -> str:
    hero = get_hero_by_id(hero_id)
    return hero.localized_name if hero else f"Hero {hero_id}"


def search_heroes(query: str, limit: int = 10) -> list[Hero]:
    """Fuzzy search heroes by localized name."""
    q = query.lower().strip()
    if not q:
        return get_all_heroes()[:limit]
    results = []
    for h in _load_heroes():
        name = h.localized_name.lower()
        if q in name:
            results.append(h)
    results.sort(key=lambda h: h.localized_name.lower().index(q))
    return results[:limit]


def reload_heroes() -> None:
    """Clear the hero cache so data is reloaded on next access."""
    _load_heroes.cache_clear()
