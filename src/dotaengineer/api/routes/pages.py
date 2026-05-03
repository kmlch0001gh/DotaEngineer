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
    best_roles = role_service.get_best_per_role(con, limit=1)
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
