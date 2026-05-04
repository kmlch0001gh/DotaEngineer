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

# Start web server
dotaengineer serve
dotaengineer serve --port 3000 --reload

# Database
dotaengineer init-db              # create schema + migrations (auto on serve)

# Players
dotaengineer add-player USERNAME --display-name "Name"

# ELO
dotaengineer recalc-elo           # recalculate all ratings from scratch

# Hero data (needs internet)
dotaengineer fetch-heroes         # download from OpenDota API

# Replay parsing
dotaengineer setup-parser         # build Java parser JAR (needs Java 17+ & Maven)
dotaengineer parse FILE.dem       # parse single replay → create match
dotaengineer parse-new [DIR]      # parse only new replays (incremental, default: data/replays)

# Backfill (safe to run multiple times, does NOT touch claims/ELO)
dotaengineer backfill-bans [DIR]         # add bans from replays to existing matches
dotaengineer backfill-achievements [DIR] # add multi-kills/streaks/courier kills from replays

# Watch for new replays
dotaengineer watch --dir PATH     # auto-parse new .dem files

# Backup
dotaengineer backup               # timestamped DB backup
```

## Environment

Required in `.env`:
- `DATABASE_URL` — PostgreSQL connection string (default: `postgresql://localhost:5432/dotacafe`)
- `ADMIN_TOKEN` — token for admin access at `/admin?token=...` (default: `changeme`)
- `CAFE_NAME` — display name for the cafe (default: "Dota Cafe")
- `REPLAY_WATCH_DIR` — optional: directory to watch for new .dem files

## Deployment

- **Production**: Hugging Face Spaces (Docker SDK) + Neon PostgreSQL
- **Dockerfile**: `python:3.13-slim`, port 7860 (HF default), `uvicorn` ASGI server
- **README.md** must have HF Spaces YAML frontmatter (`sdk: docker`, `app_port: 7860`)
- **Push to deploy**: `git push hf main` (remote `hf` points to HF Spaces repo)
- **Safe migrations**: Schema uses `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN IF NOT EXISTS` in a `DO $$ ... END $$` block — never drops tables or columns

## Architecture

### Data flow

```
Dota 2 LAN Game (host PC, map dota captain_mode)
    → .dem replay file (tv_autorecord 1)
         ↓
    Java clarity parser (full stats) OR Python CDemoFileInfo reader (basic)
         ↓
    FastAPI + Jinja2/HTMX web app (:8000 local, :7860 prod)
         ↓
    PostgreSQL database (Neon in prod, local in dev)
         ↓
    Responsive web UI (mobile-first, dark theme, offline CSS)
    ├── Dashboard (stats, top heroes picked/banned, top 5 per role, recent matches)
    ├── Match history (paginated) + detail with claim/unclaim buttons
    ├── Player profiles (stats, achievements, role scores, hero breakdown, MMR chart)
    ├── ELO leaderboard
    ├── Auto-balance teams tool
    └── Player comparison (side-by-side stats, roles, shared heroes, MMR overlay)
```

### Key design decisions

**PostgreSQL via Neon.** Production uses Neon serverless PostgreSQL. Connection pool (psycopg3 + psycopg-pool) per-request via FastAPI dependency injection. `Connection` wrapper in `db.py` translates `?` → `%s` for DuckDB-compatible query syntax.

**Offline-first.** HTMX (`static/htmx.min.js`) and all CSS are inline in `base.html`. Hero/item icons use Valve CDN URLs. Heroes data is a static JSON file (`static/heroes.json`).

**Two-layer replay parser.** Java clarity 4.0.0 parser extracts full stats (KDA, GPM, damage, items, bans, wards, multi-kills, kill streaks, courier/tormentor kills). Pure Python `dem_reader.py` fallback extracts basic data (heroes, teams, winner, duration). Java parser requires one-time setup (`dotaengineer setup-parser`).

**Team-based ELO.** K=48 for first 10 games (calibration), K=32 after. Floor at 100 MMR. `recalculate_all()` reprocesses every match from scratch — called on claim, unclaim, force-elo, and delete.

**Admin-only writes.** Cookie-based admin via `ADMIN_TOKEN`. Login at `/admin?token=X`, sets `dotacafe_admin` cookie (30-day). `is_admin` injected into all templates. No user authentication — everyone can read.

**Player claiming flow.** After replay parsed → 10 unclaimed slots. Admin assigns player + role (pos1-pos5) per slot. When all 10 claimed → ELO auto-calculates. Unclaiming reverts ELO via full recalc.

**Role-based scoring.** Weighted formulas per position (carry prioritizes GPM/damage, support prioritizes wards/healing). Scores 0-100 normalized against cafe's best values. Breakdown clickable in player profile.

### Module structure

```
src/dotaengineer/
├── config.py              — pydantic-settings, singleton `settings`
├── db.py                  — PostgreSQL schema + pool + Connection wrapper
├── elo.py                 — Team-based ELO calculation engine
├── cli.py                 — Typer CLI (serve, parse, backfill, etc.)
├── models/
│   ├── hero.py            — Hero data loader (static JSON, CDN icons)
│   ├── player.py          — Player, PlayerCreate, PlayerStats, PlayerAchievements
│   └── match.py           — CafeMatch, MatchCreate, MatchPlayer, MatchPlayerCreate
├── services/              — Business logic (stateless, take Connection)
│   ├── match_service.py   — Match CRUD + claiming + unclaiming
│   ├── player_service.py  — Player CRUD + stats + achievements aggregation
│   ├── leaderboard_service.py — Rankings, MMR history, cafe stats, top heroes
│   ├── role_service.py    — Role performance scoring (weighted formulas per position)
│   └── balance_service.py — Auto-balance algorithm (brute-force ≤12 players)
├── api/
│   ├── app.py             — FastAPI factory, admin middleware, Jinja2 filters
│   └── routes/
│       ├── pages.py       — HTML page routes (dashboard, matches, players, compare)
│       ├── matches.py     — Match API (claim, unclaim, force-elo, delete)
│       ├── players.py     — Player API (register, edit, role breakdown)
│       └── leaderboard.py — Leaderboard + balance + recalc API
├── replay/
│   ├── parser.py          — Two-layer parser (Java → Python fallback)
│   ├── dem_reader.py      — Pure Python CDemoFileInfo reader
│   └── watcher.py         — Watchdog file observer for auto-parsing
├── templates/             — Jinja2 HTML (dark Dota theme, all CSS inline)
│   ├── base.html          — Layout, nav, all CSS vars and utilities
│   ├── index.html         — Dashboard
│   ├── compare.html       — Player comparison (stats, roles, heroes, MMR chart)
│   ├── matches/           — list.html, detail.html, create.html
│   ├── players/           — list.html, register.html, profile.html
│   ├── leaderboard/       — index.html, balance.html
│   └── partials/          — HTMX fragments (toast, claim_success, role_breakdown, etc.)
└── static/                — htmx.min.js, heroes.json
```

### Page routes

```
GET  /                    — dashboard (stats, top heroes, top per role, recent matches)
GET  /matches             — match history (paginated)
GET  /matches/{id}        — match detail (scoreboard, items, claims, aghs badges)
GET  /players             — player grid
GET  /players/register    — registration form (admin)
GET  /players/{id}        — player profile (stats, achievements, roles, heroes, MMR chart)
GET  /leaderboard         — ELO rankings (top 50)
GET  /balance             — auto-balance tool
GET  /compare?p1=ID&p2=ID — player comparison
```

### API routes (HTMX / admin-only writes)

```
POST /api/matches/{id}/claim      — claim hero slot (player_id, slot, role)
POST /api/matches/{id}/unclaim/{slot} — remove claim
POST /api/matches/{id}/force-elo  — force ELO recalc
POST /api/matches/{id}/delete     — delete match + recalc ELO
POST /api/players                 — register player
POST /api/players/{id}/edit       — update display_name/username
GET  /api/players/{id}/role-breakdown/{role} — role score breakdown (HTMX partial)
GET  /api/leaderboard             — leaderboard JSON
POST /api/balance                 — auto-balance teams
POST /api/recalc-elo              — recalculate all ELO
```

### Database tables (PostgreSQL)

- `players` — id, username, display_name, mmr, games_played, wins, losses, is_active
- `matches` — id, replay_file, played_at, duration_seconds, radiant_win, game_mode, scores, source
- `match_players` — 10 per match: hero, team, KDA, GPM/XPM, damage, items_json, won, role, wards, stun_duration, damage_taken, gold_spent_support, roshan/tower/courier/tormentor kills, multi-kill counts (double/triple/ultra/rampage), kill streak counts (killing_spree through beyond_godlike)
- `match_bans` — hero bans per match (hero_id, ban_order)
- `match_purchases` — item purchase log per slot (item_name, game_time, purchase_order)
- `mmr_history` — MMR delta per player per match (mmr_before, mmr_after, mmr_change)

### Java replay parser

Located at `tools/replay-parser/`. Uses clarity 4.0.0 (compiled from source for Dota 2 LAN compatibility).

**Build**: `mvn package -q -DskipTests` → `target/dotacafe-parser.jar` (copy to `data/`)

**Extracts per player**: KDA, GPM/XPM, net worth, last hits, denies, hero/tower damage, healing, level, final inventory (from entity state), wards placed/destroyed, camps stacked, stun duration, damage taken, gold spent on support, rune pickups, roshan/tower/courier/tormentor kills, multi-kills (double through rampage), kill streaks (killing spree through beyond godlike).

**Entity field paths**: `CDOTA_PlayerResource.m_vecPlayerTeamData[pid/2]` for KDA; `CDOTA_DataRadiant/Dire.m_vecDataTeam[teamSlot]` for team stats; `CDOTAPlayerController` for team assignment (m_iTeamNum 2=R, 3=D); `CDOTAGamerulesProxy` for winner/bans/time; `CDOTA_Unit_Hero_*` for inventory.

**LAN quirk**: Players are NOT in 0-4/5-9 order. Must read `CDOTAPlayerController.m_nPlayerID` and `m_iTeamNum`, sort by PID within team.

### Config

All settings from `src/dotaengineer/config.py` via `pydantic-settings`. Singleton `settings` imported directly. `extra="ignore"` for backwards compatibility with old .env files.
