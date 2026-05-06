"""Leaderboard and auto-balance API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from dotaengineer.api.app import get_db, is_admin, templates
from dotaengineer.db import Connection
from dotaengineer.services import balance_service, leaderboard_service

router = APIRouter(prefix="/api", tags=["leaderboard"])


@router.get("/leaderboard", response_class=JSONResponse)
def leaderboard_json(
    limit: int = 50,
    con: Connection = Depends(get_db),
):
    return leaderboard_service.get_leaderboard(con, limit=limit)


@router.post("/balance", response_class=HTMLResponse)
def balance_teams_endpoint(
    request: Request,
    player_roles: str = Form(...),
    con: Connection = Depends(get_db),
):
    """Auto-balance teams from selected players with roles.

    Expects player_roles as "id:role,id:role,..." e.g. "1:pos1,2:pos3,..."
    """
    try:
        pairs = [x.strip().split(":") for x in player_roles.split(",") if x.strip()]
        role_map = {int(p[0]): p[1] for p in pairs}
    except (ValueError, IndexError):
        return templates.TemplateResponse(
            request,
            "partials/toast.html",
            {"message": "Formato inválido. Cada jugador necesita un rol.", "type": "error"},
        )

    if len(role_map) != 10:
        return templates.TemplateResponse(
            request,
            "partials/toast.html",
            {"message": "Se necesitan exactamente 10 jugadores con rol", "type": "error"},
        )

    results = balance_service.balance_teams(role_map, con)
    if not results:
        return templates.TemplateResponse(
            request,
            "partials/toast.html",
            {"message": "No se pudieron balancear los equipos", "type": "error"},
        )

    return templates.TemplateResponse(
        request,
        "partials/balance_result.html",
        {"results": results},
    )


@router.post("/recalc-elo", response_class=HTMLResponse)
def recalc_elo(
    request: Request,
    con: Connection = Depends(get_db),
):
    """Recalculate all ELO from scratch (admin only)."""
    if not is_admin(request):
        return HTMLResponse(status_code=403)
    from dotaengineer.elo import recalculate_all

    count = recalculate_all(con)
    return templates.TemplateResponse(
        request,
        "partials/toast.html",
        {"message": f"ELO recalculado: {count} partidas procesadas", "type": "success"},
    )
