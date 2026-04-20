"""FastAPI routes — JSON API for the draft tool and meta queries.

Useful for building a frontend or integrating with Discord bots, overlays, etc.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from dotaengineer.analysis.draft import DraftAnalyzer
from dotaengineer.analysis.meta import MetaAnalyzer
from dotaengineer.analysis.player_performance import PlayerPerformanceAnalyzer
from dotaengineer.config import settings

app = FastAPI(
    title="DotaEngineer API",
    description="High-MMR Dota 2 analysis — draft, meta, and personal performance",
    version="0.1.0",
)

_draft = DraftAnalyzer()
_meta = MetaAnalyzer()


# ── Meta ───────────────────────────────────────────────────────────────────────

@app.get("/meta/tierlist")
def tierlist(
    min_pick_rate: float = Query(0.03),
    min_matches: int = Query(200),
):
    try:
        df = _meta.tier_list(min_pick_rate=min_pick_rate, min_matches=min_matches)
        return df.to_dicts()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/meta/sleepers")
def sleepers(
    max_pick_rate: float = Query(0.06),
    min_win_rate: float = Query(0.52),
):
    try:
        df = _meta.sleeper_picks(max_pick_rate=max_pick_rate, min_win_rate=min_win_rate)
        return df.to_dicts()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/meta/roles")
def role_meta():
    try:
        df = _meta.role_meta()
        return df.to_dicts()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Draft ──────────────────────────────────────────────────────────────────────

class DraftRequest(BaseModel):
    my_team: list[int] = []
    enemy_team: list[int]
    pool: list[int] | None = None
    top_n: int = 5


@app.post("/draft/best-pick")
def best_pick(req: DraftRequest):
    if not req.enemy_team:
        raise HTTPException(status_code=422, detail="enemy_team cannot be empty")
    try:
        df = _draft.get_best_pick(
            my_team=req.my_team,
            enemy_team=req.enemy_team,
            pool=req.pool,
            top_n=req.top_n,
        )
        return df.to_dicts()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/draft/analyze")
def analyze_draft(radiant: list[int], dire: list[int]):
    try:
        return _draft.analyze_draft(radiant, dire)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/draft/bans")
def ban_recommendations(top_n: int = Query(5)):
    try:
        df = _draft.get_ban_recommendations(top_n=top_n)
        return df.to_dicts()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Player ─────────────────────────────────────────────────────────────────────

@app.get("/player/performance")
def player_performance(account_id: int | None = None):
    aid = account_id or settings.my_steam_id
    if not aid:
        raise HTTPException(status_code=422, detail="Provide account_id or set MY_STEAM_ID")
    try:
        analyzer = PlayerPerformanceAnalyzer(aid)
        report = analyzer.full_report()
        return {k: v.to_dicts() for k, v in report.items()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
