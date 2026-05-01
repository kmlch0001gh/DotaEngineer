"""FastAPI application factory with Jinja2 templates and static files."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from dotaengineer.config import settings
from dotaengineer.db import get_connection, init_schema, release_connection

ADMIN_COOKIE = "dotacafe_admin"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_schema()
    yield


app = FastAPI(
    title=f"{settings.cafe_name} — Dota 2 Stats",
    description="Offline Dota 2 cybercafe stats tracker with ELO rankings",
    version="0.2.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")

templates = Jinja2Templates(directory=str(settings.template_dir))


# ── Admin check ──────────────────────────────────────────────────────────────


def is_admin(request: Request) -> bool:
    """Check if the current request has admin privileges."""
    return request.cookies.get(ADMIN_COOKIE) == settings.admin_token


class AdminContextMiddleware(BaseHTTPMiddleware):
    """Injects is_admin into request.state for all requests."""

    async def dispatch(self, request: Request, call_next):
        request.state.is_admin = is_admin(request)
        return await call_next(request)


app.add_middleware(AdminContextMiddleware)

# Make is_admin available in all templates via a context processor
_original_template_response = templates.TemplateResponse


def _patched_template_response(request, name, context=None, **kwargs):
    ctx = context or {}
    ctx["is_admin"] = getattr(request.state, "is_admin", False)
    return _original_template_response(request, name, ctx, **kwargs)


templates.TemplateResponse = _patched_template_response


# ── Admin login/logout routes ────────────────────────────────────────────────


@app.get("/admin", response_class=HTMLResponse)
def admin_login(request: Request, token: str = ""):
    if token == settings.admin_token:
        response = RedirectResponse("/", status_code=302)
        response.set_cookie(ADMIN_COOKIE, token, httponly=True, max_age=60 * 60 * 24 * 30)
        return response
    return HTMLResponse("<h3>Token invalido</h3>", status_code=403)


@app.get("/logout", response_class=HTMLResponse)
def admin_logout():
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie(ADMIN_COOKIE)
    return response


# ── DB dependency ────────────────────────────────────────────────────────────


def get_db():
    """FastAPI dependency: yields a DB connection per request."""
    con = get_connection()
    try:
        yield con
    finally:
        release_connection(con)


# ── Template globals and filters ─────────────────────────────────────────────

templates.env.globals["cafe_name"] = settings.cafe_name


def _hero_icon(hero_id: int) -> str:
    """Jinja2 filter: hero_id → small icon CDN URL."""
    from dotaengineer.models.hero import get_hero_by_id

    hero = get_hero_by_id(hero_id)
    if hero and hero.icon:
        return hero.icon
    if hero:
        short = hero.name.replace("npc_dota_hero_", "")
        return f"https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/icons/{short}.png"
    return ""


templates.env.filters["hero_icon"] = _hero_icon


# ── Route modules ────────────────────────────────────────────────────────────

from dotaengineer.api.routes import leaderboard, matches, pages, players  # noqa: E402

app.include_router(pages.router)
app.include_router(matches.router)
app.include_router(players.router)
app.include_router(leaderboard.router)
