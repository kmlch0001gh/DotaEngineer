"""Player API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from dotaengineer.api.app import get_db, is_admin, templates
from dotaengineer.db import Connection
from dotaengineer.models.player import PlayerCreate
from dotaengineer.services import player_service

router = APIRouter(prefix="/api/players", tags=["players"])


@router.post("", response_class=HTMLResponse)
def register_player(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
    con: Connection = Depends(get_db),
):
    """Register a new player (admin only)."""
    if not is_admin(request):
        return HTMLResponse(status_code=403)

    existing = player_service.get_player_by_username(username, con)
    if existing:
        return templates.TemplateResponse(
            request,
            "partials/toast.html",
            {"message": f"El usuario '{username}' ya existe", "type": "error"},
        )

    try:
        data = PlayerCreate(username=username, display_name=display_name)
    except Exception:
        return templates.TemplateResponse(
            request,
            "partials/toast.html",
            {"message": "Datos inválidos. Username: 2-20 chars (a-z, 0-9, _).", "type": "error"},
        )

    player_id = player_service.create_player(data, con)
    return HTMLResponse(headers={"HX-Redirect": f"/players/{player_id}"}, content="")


@router.post("/{player_id}/edit", response_class=HTMLResponse)
def edit_player(
    request: Request,
    player_id: int,
    display_name: str = Form(...),
    username: str = Form(...),
    con: Connection = Depends(get_db),
):
    """Update a player's name (admin only)."""
    if not is_admin(request):
        return HTMLResponse(status_code=403)

    existing = player_service.get_player_by_username(username, con)
    if existing and existing.id != player_id:
        return templates.TemplateResponse(
            request,
            "partials/toast.html",
            {"message": f"El usuario '{username}' ya está en uso", "type": "error"},
        )

    player_service.update_player(player_id, display_name, username, con)
    return HTMLResponse(headers={"HX-Redirect": f"/players/{player_id}"}, content="")


@router.get("/{player_id}/role-breakdown/{role}", response_class=HTMLResponse)
def role_breakdown(
    request: Request,
    player_id: int,
    role: str,
    con: Connection = Depends(get_db),
):
    """Return role score breakdown as HTML partial."""
    from dotaengineer.services.role_service import get_role_score_breakdown

    breakdown = get_role_score_breakdown(player_id, role, con)
    return templates.TemplateResponse(
        request,
        "partials/role_breakdown.html",
        {"breakdown": breakdown, "role": role},
    )
