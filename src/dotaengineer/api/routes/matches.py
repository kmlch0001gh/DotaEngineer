"""Match CRUD API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from dotaengineer.api.app import get_db, is_admin, templates
from dotaengineer.db import Connection
from dotaengineer.services import match_service

router = APIRouter(prefix="/api/matches", tags=["matches"])


@router.post("/{match_id}/claim", response_class=HTMLResponse)
def claim_slot(
    request: Request,
    match_id: int,
    player_id: int = Form(...),
    slot: int = Form(...),
    con: Connection = Depends(get_db),
):
    """Claim a hero slot in a match (admin only)."""
    if not is_admin(request):
        return templates.TemplateResponse(
            request,
            "partials/toast.html",
            {"message": "Solo el admin puede reclamar slots", "type": "error"},
        )

    success = match_service.claim_slot(match_id, slot, player_id, con)
    if not success:
        return templates.TemplateResponse(
            request,
            "partials/toast.html",
            {"message": "No se pudo reclamar (ya reclamado o jugador duplicado)", "type": "error"},
        )

    from dotaengineer.services.player_service import get_player

    player = get_player(player_id, con)
    return templates.TemplateResponse(
        request,
        "partials/claim_success.html",
        {"player": player},
    )


@router.post("/{match_id}/unclaim/{slot}", response_class=HTMLResponse)
def unclaim_slot(
    request: Request,
    match_id: int,
    slot: int,
    con: Connection = Depends(get_db),
):
    """Remove a player claim from a slot (admin only)."""
    if not is_admin(request):
        return HTMLResponse(status_code=403)
    match_service.unclaim_slot(match_id, slot, con)
    return HTMLResponse(headers={"HX-Redirect": f"/matches/{match_id}"}, content="")


@router.post("/{match_id}/force-elo", response_class=HTMLResponse)
def force_elo(
    request: Request,
    match_id: int,
    con: Connection = Depends(get_db),
):
    """Force ELO calculation (admin only)."""
    if not is_admin(request):
        return HTMLResponse(status_code=403)
    from dotaengineer.elo import process_match_elo

    process_match_elo(match_id, con)
    return HTMLResponse(headers={"HX-Redirect": f"/matches/{match_id}"}, content="")


@router.post("/{match_id}/delete", response_class=HTMLResponse)
def delete_match(
    request: Request,
    match_id: int,
    con: Connection = Depends(get_db),
):
    """Delete a match (admin only)."""
    if not is_admin(request):
        return HTMLResponse(status_code=403)
    from dotaengineer.elo import recalculate_all

    match_service.delete_match(match_id, con)
    recalculate_all(con)
    return HTMLResponse(headers={"HX-Redirect": "/matches"}, content="")
