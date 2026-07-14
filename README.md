# TLE-Tracking

**Language / 语言**: [English](#) | [中文](README.zh.md)

---

A lightweight orbital monitoring system with dual data sources, Web Dashboard, and Telegram Bot.

## Features

- **TLE Monitoring** — Dual-source (Space-Track / CelesTrak) automated polling with failover
- **Change Classification** — Distinguishes real maneuvers from corrections (hash comparison + optional xpropagator residual analysis)
- **New Object Discovery** — Space-Track SATCAT new PAYLOAD detection with Telegram push
- **Telegram Bot** — Bidirectional control: toggle switch, manage watch list (commands + inline keyboard)
- **Web Dashboard** — Vue 3 real-time orbital data, trend charts, decay status
- **Decay Analysis** — Four-tier decay detection with alert levels
- **Docker** — Multi-arch image, `docker compose up -d`

## Quick Start

### 1. Install

```bash
pip install requests python-dotenv pyyaml fastapi uvicorn
```

### 2. Configure

Copy `.env.example` to `.env` and fill in credentials (Space-Track optional if using CelesTrak as primary):

```env
SPACETRACK_USER=your_email@example.com
SPACETRACK_PASS=your_password
TELEGRAM_BOT_TOKEN=your_bot_token      # Required for new object discovery
TELEGRAM_CHAT_ID=your_chat_id          # Required for new object discovery
```

Edit `config.yaml`:

```yaml
targets:
  norad_ids: [25544, 48273]

data_source:
  primary: "celestrak"       # No auth required
  fallback: "spacetrack"

new_object_discovery:
  enabled: true              # Enable discovery
  watched_launches:          # Optional watch list
    - intldes_prefix: "2026-085"
      label: "Starlink G12-3"
```

Fields marked `# web:` can be edited from the Dashboard Settings page with hot-reload.

### 3. Run

```bash
python spacetrack_monitor.py                  # Monitor + built-in web server
.venv\Scripts\python.exe telegram_bot.py       # Telegram Bot (separate process)
```

### 4. Docker

```bash
docker compose up -d          # Monitor + Dashboard + Bot
```

Visit `http://localhost:8000`. Bot auto-starts when Telegram credentials are configured. Pre-built image: `ghcr.io/beluga114/tle-tracking:latest`.

### 5. Local Dev

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000   # Backend
cd frontend && pnpm install && pnpm dev                         # Frontend (:5173)
```

## New Object Discovery & Telegram Bot

Queries Space-Track SATCAT daily at 17:10 UTC for newly cataloged PAYLOAD objects, pushes to Telegram.

```
Space-Track SATCAT → new_object_watcher.py → Telegram notification
                                              └── Web settings page
```

**Bot commands**:

| Command | Action |
|---|---|
| `/start` | Main menu |
| `/status` | Status + toggle |
| `/watchlist` | Manage watch list |
| `/addwatch <prefix> [label]` | Add to watch list |
| `/rmwatch <prefix>` | Remove from watch list |
| `/help` | Help |

Watch list uses prefix matching (`2026-085` matches `2026-085A`/`2026-085B`). Matched objects are pushed regardless of master switch, tagged "Watched".

## Web Dashboard

| Page | Route | Description |
|---|---|---|
| Dashboard | `/` | Satellite table, search, altitude chart |
| TLE History | `/history` | Change timeline, parameter diff |
| Decay Status | `/decay` | Phase pie chart, scatter plot, level list |
| Satellite | `/satellite/{id}` | Full params, trend charts, history |
| Settings | `/settings` | Online config editing, hot-reload |

Tech: Vue 3 + FastAPI + WebSocket + ECharts + CesiumJS

## Configuration Reference

```yaml
user_agent: ''

targets:
  norad_ids: [25544]          # web

schedule:
  minute: 17                  # Space-Track query minute (avoid :00/:30)

files:
  data_dir: /data
  data_file: tle_data.jsonl
  cache: tle_cache.json
  run_log: tle_log.jsonl
  max_log_size_mb: 10

alerts:
  reentry_warning_km: 200             # web
  only_print_on_update: true          # web
  fallback_maneuver_threshold_km: 5.0 # web

retry:
  login_max_failures: 5
  login_pause_seconds: 1800
  request_max_retries: 3
  request_retry_base: 5

xpropagator:
  enabled: true               # web
  host: localhost
  port: 50051
  maneuver_threshold_km: 5.0  # web

data_source:
  primary: celestrak
  fallback: spacetrack
  fallback_threshold: 3       # web
  celestrak_interval_seconds: 7200
  use_supplemental: false

new_object_discovery:
  enabled: false              # web
  schedule_hour: 17
  schedule_minute: 10
  backtrack_hours: 72
  daily_summary: false        # web
  watched_launches: []        # web
```

Fields marked `# web` can be edited online at `/settings`, taking effect on the next polling cycle.

## Data Files

Auto-generated in `DATA_DIR`:

> **Priority**: `DATA_DIR` env var > `config.yaml` `files.data_dir` > platform default.
> Docker: `/data` (mount to host `./data`). Windows: project directory.

- `tle_data.jsonl` — Core orbital records with `change_type` (initial/correction/maneuver/decaying)
- `tle_cache.json` — Breakpoint recovery cache
- `tle_log.jsonl` — Runtime log
- `new_object_cursor.json` — New object discovery cursor

Logs auto-rotate at 10 MB.

## Reentry Prediction

BSTAR-based simplified atmospheric model. Extremely rough estimate, for entertainment only. Ignores attitude, solar activity, space weather — errors can be several times actual. For serious decay analysis, use professional propagators (SGP4/SGP4-XP) with high-fidelity atmosphere models.

## Orbital Prediction (xpropagator)

Optional high-precision residual analysis: propagates old TLE to new epoch, computes ECI position difference.

- Residual >= threshold → Maneuver
- Residual < threshold → Correction

Requires separate [xpropagator](https://github.com/xpropagation/xpropagator) deployment. This repo does not contain SGP4 binaries.

## Rate Limits

- **Space-Track**: gp 1 req/hour, satcat_debut 1 req/day. Violations → account suspension
- **CelesTrak**: 1 query per satellite per 2 hours

Avoid :00 and :30 peak times. Do not modify scheduling logic to circumvent limits.

## Links

- [Space-Track.org](https://www.space-track.org/)
- [CelesTrak.org](https://celestrak.org/)
- [xpropagator](https://github.com/xpropagation/xpropagator)
