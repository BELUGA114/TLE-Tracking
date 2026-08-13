# TLE-Tracking

**Language / 语言**: [English](#) | [中文](README.md)

---

A lightweight orbital monitoring system with dual data sources, Web Dashboard, and Telegram Bot.

## Features

- **TLE Monitoring** — Dual-source (Space-Track / CelesTrak) automated polling with failover
- **Change Classification** — Distinguishes real maneuvers from corrections (hash comparison + optional xpropagator residual analysis)
- **New Object Discovery** — Space-Track SATCAT new PAYLOAD detection with Telegram push
- **Telegram Bot** — Bidirectional control: toggle switch, manage watch list (commands + inline keyboard)
- **Web Dashboard** — Vue 3 real-time orbital data, trend charts, decay status
- **Decay Analysis** — Four-tier decay detection with alert levels
- **Docker** — Build locally or pull the multi-arch pre-built image

## Quick Start

### 1. Configure (shared by local and Docker deployments)

Copy `.env.example` to `.env` and fill in credentials (Space-Track optional if using CelesTrak as primary):

```env
SPACETRACK_USER=your_email@example.com
SPACETRACK_PASS=your_password
TELEGRAM_BOT_TOKEN=your_bot_token      # Required for new object discovery
TELEGRAM_CHAT_ID=your_chat_id          # Required for new object discovery
DASHBOARD_API_KEY=long_random_value    # Required for configuration writes in production
```

> **How to get Telegram credentials:**
> - `TELEGRAM_BOT_TOKEN` — Message [@BotFather](https://t.me/BotFather) on Telegram, `/newbot`, follow the prompts
> - `TELEGRAM_CHAT_ID` — Send `/id` to [@UserIDxBot](https://t.me/UserIDxBot) to view your digital ID, or send a message to your bot and check `https://api.telegram.org/bot{TOKEN}/getUpdates`

The backend and Telegram Bot read the same `DASHBOARD_API_KEY` from their runtime environment. On first use, enter that value in the Web settings page's write-authentication section and store it in the current browser. The Bot normally needs no extra setup; after a rotation or for temporary recovery, send `/setapikey <key>` from the authorized `TELEGRAM_CHAT_ID`. This override remains in Bot memory only and resets to the environment value after restart.

`CESIUM_ION_TOKEN` is used directly by the browser to access Cesium Ion and is therefore visible in developer tools. Restrict the token to the deployed origins and required assets in the Cesium Ion console. When it is unset, the frontend falls back to OpenStreetMap.


Edit `config.yaml`:

```yaml
targets:
  norad_ids: [25544, 48273]

data_source:
  primary: celestrak         # No auth required
  fallback: none

new_object_discovery:
  enabled: true              # Push all new PAYLOAD objects
  watched_launches:          # Always active (ignores enabled), prefix match
    - intldes_prefix: 2026-085
      label: Starlink G12-3
```

### 2. Local Deployment

Requirements: Python 3.11+, Node.js 22+, and pnpm (available through Corepack).

Install the backend and frontend dependencies, then build the frontend:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt

corepack enable
cd frontend
pnpm install
pnpm build
cd ..
```

Start the monitor, dashboard, and Telegram bot in separate terminals:

```bash
python spacetrack_monitor.py
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
python telegram_bot.py          # Optional: start only when Telegram credentials are configured
```

Visit `http://localhost:8000`.

### 3. Docker Deployment

Requirements: Docker Engine and Docker Compose v2. Both options use the `.env`, `config.yaml`, and `./data` volume in the current directory.

#### Option A: Build Locally

```bash
docker compose up -d --build
```

#### Option B: Pull the Pre-built Image

```bash
docker compose pull
docker compose up -d --no-build
```

The pre-built image is `ghcr.io/beluga114/tle-tracking:latest`. The container starts the monitor and dashboard, and it also starts the bot when Telegram credentials are configured. Visit `http://localhost:8000`.

**Proxy (optional):** Add to `.env` if external services (Telegram, Space-Track) need a proxy:

```env
HTTP_PROXY=http://host:port
HTTPS_PROXY=http://host:port
```

The container inherits these via `docker-compose.yml`. `NO_PROXY=localhost,127.0.0.1,::1` is preset — internal API calls (bot → dashboard on localhost:8000) bypass the proxy, Leave unset or empty if no proxy is required.

### 4. Frontend Development (optional)

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000   # Backend
cd frontend && pnpm install && pnpm dev                        # Frontend (:5173)
```

## New Object Discovery & Telegram Bot

When `enabled: true`, pushes ALL newly cataloged PAYLOAD objects. `watched_launches` runs independently — prefix matches always push regardless of the master switch or `enabled` status.

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
# HTTP User-Agent header. Optional, leave empty to omit.
user_agent: ''

targets:
  norad_ids: [25544]          # web: NORAD IDs to monitor, accepts multiple

schedule:
  minute: 17                  # Space-Track query minute of the hour (avoid :00/:30 peak)

files:
  data_dir: /data             # Data directory. Docker: /data. Windows: project dir
  data_file: tle_data.jsonl   # Orbital data filename
  cache: tle_cache.json       # Breakpoint recovery cache filename
  run_log: tle_log.jsonl      # Runtime log filename
  max_log_size_mb: 10         # Auto-rotate log when exceeding this size (MB)

alerts:
  reentry_warning_km: 200             # web: Periapsis below this triggers reentry alert
  only_print_on_update: true          # web: Only print on TLE changes. Disable to see every poll
  fallback_maneuver_threshold_km: 5.0 # web: Simple maneuver threshold when xpropagator is offline (km)

retry:
  login_max_failures: 5       # Max consecutive Space-Track login failures before giving up
  login_pause_seconds: 1800   # Wait time after login failure (seconds)
  request_max_retries: 3      # Max HTTP request retries
  request_retry_base: 5       # Exponential backoff base (seconds): base × 2^(attempt-1)

xpropagator:
  enabled: true               # web: Enable high-precision residual analysis (requires separate xpropagator deployment)
  host: localhost             # gRPC server host
  port: 50051                 # gRPC server port
  maneuver_threshold_km: 5.0  # web: Residual above this is classified as a real maneuver (km)

data_source:
  primary: celestrak          # Primary source (celestrak / spacetrack)
  fallback: spacetrack        # Fallback source (spacetrack / none) — auto-switch on primary failure
  fallback_threshold: 3       # web: Switch to fallback after N consecutive primary failures
  celestrak_interval_seconds: 7200    # CelesTrak polling interval (seconds). API compliance: >= 7200
  use_supplemental: false     # Use CelesTrak supplemental GP data

new_object_discovery:
  enabled: false              # web: Enable new PAYLOAD discovery (requires Telegram credentials)
  schedule_hour: 17           # Daily check hour (UTC), after the 17:00 SATCAT update
  schedule_minute: 10         # Check minute, 10-min buffer for SATCAT refresh
  backtrack_hours: 72         # Downtime recovery window (hours). Beyond this, send summary only
  daily_summary: false        # web: Send a "no new objects today" confirmation even when empty
  watched_launches: []        # web: Priority watch list. Matches push regardless of master switch
                              # Each entry: intldes_prefix (required) + label (optional)
                              # Example:
                              #   - intldes_prefix: "2026-085"
                              #     label: "Starlink G12"
                              #   - intldes_prefix: "2026-092"
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
