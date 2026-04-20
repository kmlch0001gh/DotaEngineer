# DotaEngineer

Data engineering and analysis platform for **high-MMR Dota 2 decision-making**.

Built by a 7600 MMR player / data engineer to answer questions that OpenDota, Stratz, and Dota2ProTracker don't answer well at the 8k bracket.

---

## What this solves

| Question | Where existing tools fall short |
|---|---|
| "What should I pick against this lineup?" | Generic counters across all MMRs — not filtered to immortal |
| "Am I farming below the 8k curve?" | No per-hero GPM benchmark at high MMR |
| "Which heroes should I drop from my pool?" | No personal WR vs meta baseline |
| "What's currently broken in the meta?" | No sleeper-pick analysis; tier lists are subjective |
| "How is my recent form?" | No rolling win-rate trend |

---

## Architecture

```
OpenDota API ─┐
Stratz API   ─┤─▶ Prefect Pipelines ─▶ DuckDB (warehouse.duckdb)
Steam API    ─┘                              │
                                             ▼
                                         dbt models
                                      (staging → marts)
                                             │
                              ┌──────────────┼──────────────┐
                              ▼              ▼              ▼
                        FastAPI API    Streamlit        Notebooks
                         (:8000)      Dashboard       (exploration)
```

**Stack:** Python 3.11, Polars, DuckDB, dbt, Prefect, FastAPI, Streamlit, Plotly

---

## Quick start

```bash
# 1. Clone and install
git clone <repo>
cd dotaengineer
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Configure
cp .env.example .env
# Edit .env: add OPENDOTA_API_KEY, STRATZ_API_TOKEN, MY_STEAM_ID

# 3. Start infrastructure
docker compose up -d

# 4. Run pipelines
dotaengineer ingest meta          # Hero meta from OpenDota + Stratz
dotaengineer ingest player        # Your match history

# 5. Explore
jupyter notebook notebooks/01_meta_exploration.ipynb

# Or launch dashboard
dotaengineer serve dashboard

# Or API
dotaengineer serve api
```

---

## CLI reference

```
dotaengineer ingest meta                          # Daily meta pipeline
dotaengineer ingest player --limit 500            # Personal history
dotaengineer analyze counters "74,14,44"          # Counter-picks
dotaengineer analyze counters "74,14,44" \
  --allies "1,2" --pool "3,4,5,6"                # With pool restriction
dotaengineer analyze performance                  # Personal report
dotaengineer analyze meta                         # Tier list in terminal
dotaengineer serve api --reload                   # Dev API server
dotaengineer serve dashboard                      # Streamlit
```

---

## Key analyses

### Draft tool
- **Counter-pick score**: weighted average matchup advantage across all enemy heroes
- **Synergy score**: duo win rate advantage with allied heroes
- **Combined score**: 60% counter + 40% synergy (adjustable)
- **Ban recommendations**: WR × √PR priority score

### Meta
- **Tier list**: S/A/B/C at immortal bracket with scatter WR vs PR
- **Sleeper picks**: high WR, low PR/ban — unexploited advantage
- **Patch delta**: win rate shift per hero between patches
- **Role meta**: strongest position in current patch

### Personal performance
- **Hero pool efficiency**: your WR minus meta WR per hero
- **Farm deficit**: your GPM vs immortal bracket average per hero
- **Laning stats**: CS, kill participation, deaths per lane
- **Duration splits**: WR in <25 / 25-40 / >40 min games
- **Rolling form**: 10-game rolling win rate over last 50 matches

---

## Project structure

```
dotaengineer/
├── src/dotaengineer/
│   ├── ingestion/          # API clients (OpenDota, Stratz)
│   ├── pipelines/          # Prefect flows (meta, player)
│   ├── analysis/           # DuckDB-backed analysis (draft, meta, performance)
│   ├── api/                # FastAPI routes
│   ├── dashboard/          # Streamlit app
│   ├── models/             # Pydantic data models
│   ├── config.py           # Pydantic settings
│   └── cli.py              # Typer CLI
├── dbt/
│   └── models/
│       ├── staging/        # Raw → cleaned views
│       ├── intermediate/   # Business logic
│       └── marts/          # Final tables (hero_meta_immortal, hero_matchups_immortal)
├── notebooks/              # Exploratory analysis
├── tests/                  # Unit + integration tests
├── docker-compose.yml      # PostgreSQL + Prefect server
└── pyproject.toml
```

---

## Roadmap

- [ ] **Matchup pipeline**: Fetch `/heroes/{id}/matchups` for all 124 heroes → full matrix
- [ ] **Pro tracker integration**: Mirror top-200 immortal accounts, patch pro heroes
- [ ] **Draft overlay**: In-game floating window (Electron or PyWebView)
- [ ] **Time-series benchmarks**: GPM/XPM curves vs peers at same net worth timing
- [ ] **Ward heatmaps**: Observer/sentry placement analysis at immortal
- [ ] **Replay parser**: Deep laning phase analytics from actual replay files
