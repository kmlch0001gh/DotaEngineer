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
def balance_teams(
    request: Request,
    player_ids: str = Form(...),
    con: Connection = Depends(get_db),
):
    """Auto-balance teams from selected players."""
    try:
        ids = [int(x.strip()) for x in player_ids.split(",") if x.strip()]
    except ValueError:
        return templates.TemplateResponse(
            request,
            "partials/toast.html",
            {"message": "IDs de jugadores inválidos", "type": "error"},
        )

    if len(ids) < 2:
        return templates.TemplateResponse(
            request,
            "partials/toast.html",
            {"message": "Se necesitan al menos 2 jugadores", "type": "error"},
        )

    result = balance_service.balance_teams(ids, con)
    if not result:
        return templates.TemplateResponse(
            request,
            "partials/toast.html",
            {"message": "No se pudieron balancear los equipos", "type": "error"},
        )

    return templates.TemplateResponse(
        request,
        "partials/balance_result.html",
        {"result": result},
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
