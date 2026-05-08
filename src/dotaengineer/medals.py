"""Dota 2 medal/rank badge system adapted for cafe MMR range."""

STRATZ_CDN = "https://cdn.stratz.com/images/dota2/seasonal_rank"

TIERS: list[tuple[int, str, int]] = [
    (1, "Herald", 100),
    (2, "Guardian", 300),
    (3, "Crusader", 500),
    (4, "Archon", 700),
    (5, "Legend", 900),
    (6, "Ancient", 1100),
    (7, "Divine", 1300),
    (8, "Immortal", 1500),
]

STAR_LABELS = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}

TIER_SPAN = 200  # MMR range per tier (except Immortal)
STAR_SPAN = 40  # MMR range per star (200 / 5)


def get_medal(mmr: int) -> dict[str, object]:
    """Return medal info for a given MMR value.

    Returns dict with keys: tier, tier_name, stars, stars_label, label,
    medal_url, star_url (None for Immortal).
    """
    tier_num = 1
    tier_name = "Herald"
    tier_floor = 100

    for t_num, t_name, t_floor in TIERS:
        if mmr >= t_floor:
            tier_num = t_num
            tier_name = t_name
            tier_floor = t_floor

    medal_url = f"{STRATZ_CDN}/medal_{tier_num}.png"

    if tier_num == 8:  # Immortal — no stars
        return {
            "tier": tier_num,
            "tier_name": tier_name,
            "stars": 0,
            "stars_label": "",
            "label": tier_name,
            "medal_url": medal_url,
            "star_url": None,
        }

    stars = min(5, max(1, (mmr - tier_floor) // STAR_SPAN + 1))
    stars_label = STAR_LABELS[stars]
    star_url = f"{STRATZ_CDN}/star_{stars}.png"

    return {
        "tier": tier_num,
        "tier_name": tier_name,
        "stars": stars,
        "stars_label": stars_label,
        "label": f"{tier_name} {stars_label}",
        "medal_url": medal_url,
        "star_url": star_url,
    }
