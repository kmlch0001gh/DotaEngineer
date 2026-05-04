"""HTML page routes — serve Jinja2 templates."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from dotaengineer.api.app import get_db, templates
from dotaengineer.db import Connection
from dotaengineer.services import (
    leaderboard_service,
    match_service,
    player_service,
    role_service,
)

router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
def home(request: Request, con: Connection = Depends(get_db)):
    stats = leaderboard_service.get_cafe_stats(con)
    leaderboard = leaderboard_service.get_leaderboard(con, limit=5)
    top_picks = leaderboard_service.get_top_heroes_picked(con, limit=5)
    top_bans = leaderboard_service.get_top_heroes_banned(con, limit=5)
    best_roles = role_service.get_best_per_role(con, limit=5)
    matches, _ = match_service.list_matches(page=1, per_page=5, con=con)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "stats": stats,
            "leaderboard": leaderboard,
            "top_picks": top_picks,
            "top_bans": top_bans,
            "best_roles": best_roles,
            "matches": matches,
        },
    )


@router.get("/matches", response_class=HTMLResponse)
def match_list(
    request: Request,
    page: int = Query(1, ge=1),
    con: Connection = Depends(get_db),
):
    matches, total = match_service.list_matches(page=page, per_page=10, con=con)
    total_pages = max(1, (total + 9) // 10)
    return templates.TemplateResponse(
        request,
        "matches/list.html",
        {"matches": matches, "page": page, "total_pages": total_pages, "total": total},
    )


@router.get("/matches/{match_id}", response_class=HTMLResponse)
def match_detail(
    request: Request,
    match_id: int,
    con: Connection = Depends(get_db),
):
    match = match_service.get_match(match_id, con)
    if not match:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"message": "Partida no encontrada", "code": 404},
            status_code=404,
        )
    players = player_service.list_players(con)
    mmr_changes = {}
    for row in con.execute(
        "SELECT player_id, mmr_change FROM mmr_history WHERE match_id = ?",
        [match_id],
    ).fetchall():
        mmr_changes[row[0]] = row[1]
    # Aghanim's status per slot: check purchase log for shard, inventory for scepter
    aghs_status = {}
    shard_rows = con.execute(
        """SELECT slot FROM match_purchases
           WHERE match_id = ? AND item_name = 'aghanims_shard'""",
        [match_id],
    ).fetchall()
    for (s,) in shard_rows:
        aghs_status.setdefault(s, {})["shard"] = True

    for p in match.players:
        aghs_status.setdefault(p.slot, {})
        if "ultimate_scepter" in p.final_items:
            aghs_status[p.slot]["scepter"] = True
        # Also check purchase log for scepter blessing (consumed, not in inventory)
    scepter_rows = con.execute(
        """SELECT slot FROM match_purchases
           WHERE match_id = ? AND item_name = 'ultimate_scepter'""",
        [match_id],
    ).fetchall()
    for (s,) in scepter_rows:
        aghs_status.setdefault(s, {})["scepter"] = True

    return templates.TemplateResponse(
        request,
        "matches/detail.html",
        {
            "match": match,
            "players": players,
            "mmr_changes": mmr_changes,
            "aghs_status": aghs_status,
        },
    )


@router.get("/players", response_class=HTMLResponse)
def player_list(
    request: Request,
    con: Connection = Depends(get_db),
):
    players = player_service.list_players(con)
    return templates.TemplateResponse(request, "players/list.html", {"players": players})


@router.get("/players/register", response_class=HTMLResponse)
def player_register_form(request: Request):
    return templates.TemplateResponse(request, "players/register.html")


@router.get("/players/{player_id}", response_class=HTMLResponse)
def player_profile(
    request: Request,
    player_id: int,
    con: Connection = Depends(get_db),
):
    stats = player_service.get_player_stats(player_id, con)
    if not stats:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"message": "Jugador no encontrado", "code": 404},
            status_code=404,
        )
    recent_matches = player_service.get_player_recent_matches(player_id, limit=20, con=con)
    mmr_history = leaderboard_service.get_mmr_history(player_id, con)
    mmr_by_match = {h["match_id"]: h["mmr_change"] for h in mmr_history}
    role_stats = role_service.get_player_role_stats(player_id, con)
    return templates.TemplateResponse(
        request,
        "players/profile.html",
        {
            "stats": stats,
            "recent_matches": recent_matches,
            "mmr_history": mmr_history,
            "mmr_by_match": mmr_by_match,
            "role_stats": role_stats,
        },
    )


@router.get("/leaderboard", response_class=HTMLResponse)
def leaderboard_page(
    request: Request,
    con: Connection = Depends(get_db),
):
    leaderboard = leaderboard_service.get_leaderboard(con, limit=50)
    return templates.TemplateResponse(
        request,
        "leaderboard/index.html",
        {"leaderboard": leaderboard},
    )


@router.get("/balance", response_class=HTMLResponse)
def balance_page(
    request: Request,
    con: Connection = Depends(get_db),
):
    players = player_service.list_players(con)
    return templates.TemplateResponse(
        request,
        "leaderboard/balance.html",
        {"players": players},
    )


@router.get("/heroes", response_class=HTMLResponse)
def heroes_page(
    request: Request,
    con: Connection = Depends(get_db),
):
    heroes = leaderboard_service.get_hero_stats(con)
    return templates.TemplateResponse(request, "heroes.html", {"heroes": heroes})


@router.get("/compare", response_class=HTMLResponse)
def compare_page(
    request: Request,
    p1: int | None = Query(None),
    p2: int | None = Query(None),
    con: Connection = Depends(get_db),
):
    players = player_service.list_players(con)
    ctx: dict = {"players": players, "p1_id": p1, "p2_id": p2}

    if p1 and p2 and p1 != p2:
        stats1 = player_service.get_player_stats(p1, con)
        stats2 = player_service.get_player_stats(p2, con)
        if not stats1 or not stats2:
            return templates.TemplateResponse(
                request,
                "error.html",
                {"message": "Jugador no encontrado", "code": 404},
                status_code=404,
            )

        # Role stats as dicts keyed by role
        roles1_list = role_service.get_player_role_stats(p1, con)
        roles2_list = role_service.get_player_role_stats(p2, con)
        roles1 = {r["role"]: r for r in roles1_list}
        roles2 = {r["role"]: r for r in roles2_list}

        # MMR history
        mmr1 = leaderboard_service.get_mmr_history(p1, con)
        mmr2 = leaderboard_service.get_mmr_history(p2, con)

        # Shared heroes
        heroes1 = {h.hero_id: h for h in stats1.hero_breakdown}
        heroes2 = {h.hero_id: h for h in stats2.hero_breakdown}
        shared_ids = set(heroes1) & set(heroes2)
        shared_heroes = [
            {"hero_id": hid, "hero_name": heroes1[hid].hero_name,
             "p1": heroes1[hid], "p2": heroes2[hid]}
            for hid in shared_ids
        ]
        shared_heroes.sort(key=lambda x: x["p1"].games + x["p2"].games, reverse=True)

        # Head-to-head metrics: (label, v1, v2, higher_is_better)
        p1p, p2p = stats1.player, stats2.player
        d1 = max(stats1.avg_deaths, 1)
        d2 = max(stats2.avg_deaths, 1)
        kda1 = round((stats1.avg_kills + stats1.avg_assists) / d1, 2)
        kda2 = round((stats2.avg_kills + stats2.avg_assists) / d2, 2)
        metrics = [
            ("MMR", p1p.mmr, p2p.mmr, True),
            ("Win Rate", f"{p1p.win_rate * 100:.1f}%", f"{p2p.win_rate * 100:.1f}%", True),
            ("KDA Ratio", kda1, kda2, True),
            ("GPM", int(stats1.avg_gpm), int(stats2.avg_gpm), True),
            ("Racha Actual", stats1.current_streak, stats2.current_streak, True),
            ("Mejor Racha", stats1.best_win_streak, stats2.best_win_streak, True),
            ("Partidas", p1p.games_played, p2p.games_played, None),
        ]

        ctx.update({
            "stats1": stats1,
            "stats2": stats2,
            "roles1": roles1,
            "roles2": roles2,
            "mmr1": mmr1,
            "mmr2": mmr2,
            "shared_heroes": shared_heroes,
            "metrics": metrics,
        })

    return templates.TemplateResponse(request, "compare.html", ctx)
