# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"

# Lint
ruff check src/ tests/
ruff format src/ tests/

# Type check
mypy src/

# Run all tests
pytest

# Run a single test file
pytest tests/unit/test_elo.py

# Start web server
dotaengineer serve
dotaengineer serve --port 3000 --reload

# Database
dotaengineer init-db              # create schema (auto on serve)
dotaengineer backup               # timestamped backup

# Players
dotaengineer add-player USERNAME --display-name "Name"

# ELO
dotaengineer recalc-elo           # recalculate all ratings from scratch

# Hero data (needs internet)
dotaengineer fetch-heroes         # download from OpenDota API
```

## Environment

Required in `.env` (see `.env.example`):
- `CAFE_NAME` — display name for the cafe (default: "Dota Cafe")
- `DUCKDB_PATH` — path to database file (default: `./data/cafe.duckdb`)
- `REPLAY_WATCH_DIR` — optional: Dota 2 replay directory for auto-parsing

## Architecture

### Data flow

```
Dota 2 LAN Game (host PC, map dota captain_mode)
    → .dem replay file (if tv_autorecord 1)
    → OR manual match entry via web form
         ↓
    File watcher (watchdog) OR manual upload OR web form
         ↓
    FastAPI + Jinja2/HTMX web app (same PC, :8000)
         ↓
    DuckDB database (data/cafe.duckdb)
         ↓
    Responsive web UI (mobile-first, dark theme)
    ├── Dashboard (stats, recent matches, top players)
    ├── Match history + detail with claim buttons
    ├── Player profiles (stats, hero breakdown, MMR chart)
    ├── ELO leaderboard
    └── Auto-balance teams tool
```

### Key design decisions

**DuckDB as the single database.** All data stored in `data/cafe.duckdb`. Connections are opened per-request via FastAPI dependency injection. Schema initialized on server startup.

**Offline-first.** HTMX and all CSS are bundled in `static/`. Hero data is a static JSON file. The app works fully on LAN with no internet. CDN is never required.

**Team-based ELO.** Rating system uses team average MMR with expected score formula. K=48 for first 10 games (calibration), K=32 after. Floor at 100 MMR. ELO triggers automatically when all 10 match slots are claimed.

**Player claiming flow.** After a match is entered, players "claim" their hero slot from the match detail page. Optional 4-digit PIN for identity protection. When all 10 claimed → ELO auto-calculates.

**Auto-balance.** For ≤12 players, brute-forces all C(n, n/2) combinations to find minimum MMR difference. Returns predicted win probability per team.

### Module structure

```
src/dotaengineer/
├── config.py              — pydantic-settings, singleton `settings`
├── db.py                  — DuckDB schema + connection management
├── elo.py                 — Team-based ELO calculation engine
├── cli.py                 — Typer CLI commands
├── models/                — Pydantic v2 models
│   ├── hero.py            — Hero data loader (static JSON)
│   ├── player.py          — Player, PlayerCreate, PlayerStats
│   └── match.py           — CafeMatch, MatchCreate, MatchPlayer
├── services/              — Business logic (stateless, take DuckDB con)
│   ├── match_service.py   — Match CRUD + claiming
│   ├── player_service.py  — Player CRUD + stats aggregation
│   ├── leaderboard_service.py — Rankings + cafe stats
│   └── balance_service.py — Auto-balance algorithm
├── api/                   — FastAPI web application
│   ├── app.py             — App factory, Jinja2 + static files setup
│   └── routes/            — Route modules (pages, matches, players, leaderboard)
├── replay/                — Replay parsing (optional enhancement)
│   ├── parser.py          — .dem file parser
│   └── watcher.py         — watchdog file observer
├── templates/             — Jinja2 HTML templates (dark Dota theme)
└── static/                — Bundled assets (htmx.min.js, heroes.json, icons)
```

### API endpoints

```
Page routes (return HTML):
GET  /                         — dashboard
GET  /matches                  — match history (paginated)
GET  /matches/new              — manual match entry form
GET  /matches/{id}             — match detail + claim buttons
GET  /players                  — player list
GET  /players/register         — registration form
GET  /players/{id}             — player profile
GET  /leaderboard              — ELO rankings
GET  /balance                  — auto-balance tool

API routes (HTMX / JSON):
POST /api/matches              — create match from form
POST /api/matches/{id}/claim   — claim hero slot
POST /api/matches/{id}/force-elo — force ELO with partial claims
POST /api/matches/{id}/delete  — delete match + recalc ELO
POST /api/players              — register player
POST /api/players/hero-search  — hero autocomplete
POST /api/balance              — auto-balance teams
POST /api/recalc-elo           — recalculate all ELO
GET  /api/leaderboard          — leaderboard JSON
```

### DuckDB tables

- `players` — registered cafe players (username, display_name, mmr, wins, losses)
- `matches` — match records (played_at, radiant_win, duration, scores, source)
- `match_players` — 10 rows per match (hero, team, stats, player_id nullable until claimed)
- `mmr_history` — one row per player per match (mmr_before, mmr_after, mmr_change)

### Config

All settings come from `src/dotaengineer/config.py` via `pydantic-settings`. The singleton `settings` is imported directly. Extra env vars are ignored (backwards-compatible with old .env files).
