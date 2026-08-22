# TLE-Tracking

Language: English | [中文](README.md)

A lightweight orbital monitoring system that tracks satellite TLE updates, classifies orbital changes, and analyzes decay trends. It supports Space-Track and CelesTrak failover, with a Web dashboard and Telegram Bot.

## Features

- Dual-source TLE polling and failover
- Change classification through hashes and optional xpropagator residual analysis
- Space-Track SATCAT detection for newly cataloged PAYLOAD objects, with Telegram notifications
- Telegram Bot watch-list and toggle controls
- Vue 3 dashboard, CesiumJS 3D view, and trend charts
- Four-level decay-status classification

## Quick start

### Configure

Copy `.env.example` to `.env`. Fill in Space-Track credentials when using that source, Telegram credentials when enabling new-object notifications, and `DASHBOARD_API_KEY` in production.

```env
SPACETRACK_USER=your_email@example.com
SPACETRACK_PASS=your_password
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
DASHBOARD_API_KEY=long_random_value
```

Generate `DASHBOARD_API_KEY` with:

```bash
node -e "console.log(require('node:crypto').randomBytes(32).toString('base64url'))"
```

`CESIUM_ION_TOKEN` is optional. It is sent to the browser, so restrict its allowed origins and assets in Cesium Ion. When it is unset, the frontend uses OpenStreetMap imagery.

Edit `config.yaml` to select satellites and a data source:

```yaml
targets:
  norad_ids: [25544, 48273]

data_source:
  primary: celestrak
  fallback: none

new_object_discovery:
  enabled: true
  watched_launches:
    - intldes_prefix: 2026-085
      label: Starlink G12-3
```

### Local deployment

Requires Python 3.11+, Node.js 22+, and pnpm (available through Corepack).

```bash
python -m venv .venv
python -m pip install -r requirements.txt

corepack enable
cd frontend
pnpm install
pnpm build
cd ..
```

Start the services in separate terminals:

```bash
python spacetrack_monitor.py
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
python telegram_bot.py  # Optional when Telegram credentials are configured
```

Open `http://localhost:8000`.

### Testing

```bash
python -m pip install pytest
python -m pytest
```

Integration scripts under `scripts/` require external services:

```bash
python scripts/test_telegram_bot.py   # requires uvicorn running on localhost:8000
python scripts/test_xpropagator.py    # requires the xpropagator gRPC container
```

### Docker deployment

Requires Docker Engine and Docker Compose v2. Docker uses `.env`, `config.yaml`, and the `./data` volume in the current directory.

```bash
# Build locally
docker compose up -d --build

# Or pull the pre-built image
docker compose pull
docker compose up -d --no-build
```

The pre-built image is `ghcr.io/beluga114/tle-tracking:latest`. The container starts the monitor and dashboard, and starts the Bot when Telegram credentials are configured. Set `HTTP_PROXY` and `HTTPS_PROXY` in `.env` when external services require a proxy; localhost API calls inside the container bypass it.

### Frontend development

```bash
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
cd frontend && pnpm install && pnpm dev
```

The development server listens on `http://localhost:5173`.

## New-object discovery and Telegram Bot

`new_object_discovery.enabled: true` sends every newly cataloged PAYLOAD object. `watched_launches` matches international-designator prefixes and always sends matching objects, regardless of the master switch. For example, `2026-085` matches `2026-085A` and `2026-085B`.

| Command | Action |
| --- | --- |
| `/start` | Main menu |
| `/status` | Show status and toggle |
| `/watchlist` | Manage watch list |
| `/addwatch <prefix> [label]` | Add a watch |
| `/rmwatch <prefix>` | Remove a watch |
| `/help` | Help |

## Configuration reference

```yaml
# HTTP User-Agent header. Leave empty to omit.
user_agent: ''

targets:
  norad_ids: [25544]          # web: NORAD IDs to monitor, accepts multiple

schedule:
  minute: 17                  # Space-Track request minute each hour; avoid :00 and :30

files:
  data_dir: /data             # Data directory; /data is recommended for Docker
  data_file: tle_data.jsonl   # Orbital data filename
  cache: tle_cache.json       # Resume cache filename
  run_log: tle_log.jsonl      # Runtime log filename
  max_log_size_mb: 10         # Log rotation threshold, MB

alerts:
  reentry_warning_km: 200             # web: Warn when periapsis falls below this value
  sgp4_reliable_floor_km: 350         # Do not use SGP4 residual analysis below this altitude
  only_print_on_update: true          # web: Print only when TLE changes
  fallback_maneuver_threshold_km: 5.0 # web: Maneuver threshold without xpropagator, km

retry:
  login_max_failures: 5       # Maximum consecutive Space-Track login failures
  login_pause_seconds: 1800   # Wait after login failure, seconds
  request_max_retries: 3      # Maximum HTTP request retries
  request_retry_base: 5       # Exponential-backoff base, seconds

xpropagator:
  enabled: true               # web: Enable high-precision residual analysis; requires a separate service
  host: localhost             # gRPC server host
  port: 50051                 # gRPC server port
  maneuver_threshold_km: 5.0  # web: Residual at or above this value is a maneuver, km

data_source:
  primary: celestrak          # Primary source: celestrak or spacetrack
  fallback: spacetrack        # Fallback source: spacetrack or none
  fallback_threshold: 3       # web: Switch after this many consecutive primary-source failures
  celestrak_interval_seconds: 7200  # Per-satellite CelesTrak interval, at least 7200 seconds
  use_supplemental: false     # Use CelesTrak supplemental sup-gp data

new_object_discovery:
  enabled: false              # web: Enable new PAYLOAD discovery; requires Telegram credentials
  schedule_hour: 17           # Daily check hour, UTC
  schedule_minute: 10         # Check minute; allows 10 minutes for SATCAT refresh
  backtrack_hours: 72         # Downtime recovery window, hours
  daily_summary: false        # Send a daily confirmation when no objects are found
  watched_launches: []        # web: Priority watch list with intldes_prefix and optional label
```

Fields marked `# web` can be changed at `/settings` and take effect on the next polling cycle.

## Operational notes

Data-directory priority is `DATA_DIR` environment variable > `files.data_dir` in `config.yaml` > the platform default. Docker uses `/data` by default and mounts host `./data`.

xpropagator propagates an old TLE to the new epoch and classifies the ECI position residual: a residual at or above the configured threshold is a maneuver; otherwise it is a correction. It requires a separate [xpropagator](https://github.com/xpropagation/xpropagator) deployment. Residual analysis is not used below `sgp4_reliable_floor_km`.

Reentry prediction uses a simplified BSTAR atmospheric model and ignores attitude, solar activity, and space weather. Treat it as a rough indication only.

Respect the source limits: Space-Track gp is limited to once per hour and satcat_debut to once per day; CelesTrak requests must be at least two hours apart for each satellite. Keep scheduled requests away from :00 and :30.

## Links

- [Space-Track](https://www.space-track.org/)
- [CelesTrak](https://celestrak.org/)
- [xpropagator](https://github.com/xpropagation/xpropagator)
