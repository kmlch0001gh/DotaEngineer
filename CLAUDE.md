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
pytest tests/unit/test_models.py

# Run a single test by name
pytest tests/unit/test_models.py::test_player_kda

# Infrastructure (PostgreSQL + Prefect server)
docker compose up -d

# Pipelines
dotaengineer ingest meta
dotaengineer ingest player --limit 200

# Servers
dotaengineer serve api --reload        # FastAPI on :8000
dotaengineer serve dashboard           # Streamlit

# dbt
cd dbt && dbt run && dbt test
```

## Architecture

### Data flow

```
OpenDota REST + Stratz GraphQL
        │
        ▼
Prefect pipelines (src/pipelines/)
  → write raw JSON to data/raw/
  → load into DuckDB (data/warehouse.duckdb)
        │
        ▼
dbt models (dbt/models/)
  staging/ → intermediate/ → marts/
        │
        ▼
Analysis layer (src/analysis/)  ← reads from DuckDB
  ├── draft.py      — counter-pick / synergy scoring
  ├── meta.py       — tier list, sleeper picks, patch delta
  └── player_performance.py — personal WR vs meta baseline
        │
    ┌───┴────────┐
    ▼            ▼
FastAPI      Streamlit
(:8000)      dashboard
```

### Key design decisions

**DuckDB as the analytics engine.** All analysis classes open a DuckDB connection directly against `data/warehouse.duckdb`. There is no ORM — queries are raw SQL that returns `polars.DataFrame`. Avoid adding an ORM layer.

**Two ingestion sources with different strengths.** OpenDota provides `/heroStats`, matchup matrices, and item timing scenarios. Stratz (GraphQL) provides bracket-filtered win rates, laning outcomes, and `imp` (impact score). When both cover the same metric, Stratz immortal data takes precedence in the dbt mart (`hero_meta_immortal`).

**dbt models feed the analysis layer.** The analysis classes in `src/analysis/` query tables that dbt materialises (`hero_meta_immortal`, `hero_matchups_immortal`, `hero_duos_immortal`, etc.). If a table doesn't exist yet, the analysis query will fail — the pipeline must be run first.

**Rate limiting lives in `ingestion/base.py`.** `RateLimiter` is a token-bucket async limiter. Both `OpenDotaClient` and `StratzClient` inherit from or compose `BaseAPIClient`. All API calls go through `_get()` which enforces the limiter and applies retries via tenacity.

**All analysis classes are stateless.** They open a read-only DuckDB connection per method call. No connection pooling — DuckDB handles it.

### MMR bracket conventions

- `high_mmr_threshold` in `config.py` (default 7000) controls what counts as "high MMR" for filtering
- OpenDota rank tiers: 80 = Immortal, 70 = Divine. The pipelines filter `min_rank=70` by default
- Stratz bracket enum: `IMMORTAL` is the target for all hero stats queries

### DuckDB table naming

Tables consumed by the analysis layer follow the pattern `{entity}_{context}` (e.g. `hero_meta_immortal`, `hero_matchups_immortal`, `player_matches`). The `player_matches` table is the personal fact table — it stores one row per match per player slot for `MY_STEAM_ID`.

### Config

All settings come from `src/dotaengineer/config.py` via `pydantic-settings`. The singleton `settings` is imported directly — do not instantiate `Settings()` elsewhere.
