# TLE-Tracking

**Language / 语言**: [English](#) | [中文](README.zh.md)

---

A lightweight orbital monitoring system with a Web Dashboard, supporting dual data sources (Space-Track.org and CelesTrak).

**Core capabilities**:

- **Data Collection** — Automated TLE monitoring for single or multiple satellites with dual-source failover
- **Change Classification** — Distinguishes between solution corrections and real maneuvers (hash comparison + optional xpropagator residual analysis)
- **Web Dashboard** — real-time orbital data, trend charts, and decay status
- **Real-time Push** — WebSocket-based live updates, pages respond automatically
- **Decay Analysis** — Automatic orbital decay detection with tiered alerts
- **One-click Docker** — Monitor + Dashboard

---

## Features

- Intelligent scheduling: respects both scheduled time and API rate limits
- TLE change classification: distinguishes solution corrections from real maneuvers
  - Default simple threshold rules based on perigee/apogee
  - Optional high-precision residual analysis (requires xpropagator service)
- Breakpoint recovery: automatically recovers unprocessed data from cache after crash
- Automatic state recovery on restart: restores last orbital state from historical data

---

## Quick Start

### 1. Install Python Dependencies

```bash
pip install requests python-dotenv pyyaml
```

---

### 2. Configure Credentials

Copy `.env.example` to `.env` and fill in your Space-Track credentials (required for Space-Track mode):

```bash
cp .env.example .env
```

```env
SPACETRACK_USER=your_email@example.com
SPACETRACK_PASS=your_password
```

> **Note**: If using CelesTrak as primary source, Space-Track credentials are optional.

---

### 3. Configure Monitoring Targets and Data Source

Edit `config.yaml` to set monitored satellites and adjust parameters. Example:

```yaml
targets:
  norad_ids: [25544, 48273]

schedule:
  minute: 17

data_source:
  primary: "celestrak"
  fallback: "spacetrack"
  fallback_threshold: 3
```

> **Web hot-reload**: Editable fields (marked `# web:` in [Configuration Reference](#configuration-reference)) can be modified via the Dashboard Settings page at `/settings` — changes take effect on the next polling cycle without restart. See [Configuration Reference](#configuration-reference) below.

---

### 4. (Optional) Configure xpropagator Residual Analysis

```bash
pip install grpcio grpcio-tools
```

Enable the `xpropagator` section in `config.yaml`, then see [Orbital Prediction Backend](#orbital-prediction-backend-xpropagator) for details.

---

### 5. Run the Script

```bash
python spacetrack_monitor.py
```

On first run, the script will load configuration, perform cold start if needed, fetch data immediately, and then follow the configured schedule.

---

### 6. Docker Deployment

Build and run with Docker Compose (multi-stage build, frontend compiled automatically):

```bash
# Build and start (monitor + web dashboard)
docker compose up -d

# View logs
docker compose logs -f

# Web dashboard only (no data collection)
DISABLE_MONITOR=true docker compose up -d

# Stop
docker compose down
```

Open **http://localhost:8000** to access the dashboard.

**Host file layout**:
```
project/
├── config.yaml      # Configuration (mounted)
├── .env             # Credentials (optional)
└── data/            # Runtime data (persistent volume)
    ├── tle_data.jsonl
    ├── tle_log.jsonl
    ├── tle_cache.json
    ├── decay_state.json
    └── celestrak_poll_cache.json
```

> **Hot-reload**: Fields marked `# web:` (see [Configuration Reference](#configuration-reference) below) can be changed from the Dashboard Settings page (`/settings`) without restart. For non-editable fields, edit `config.yaml` and run `docker compose restart` (no rebuild needed).

### 7. Local Development (without Docker)

**Start backend**:

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

**Start frontend** (requires Node.js 22+ and pnpm):

```bash
cd frontend
pnpm install
pnpm dev
```

Frontend dev server runs on `http://localhost:5173` with API proxy to backend port 8000.

---

## Web Dashboard

A **Vue 3 + FastAPI + WebSocket** dashboard that visualizes orbital data in real-time.

| Page | Route | Description |
|---|---|---|
| **Dashboard** | `/` | Satellite table, search/filter, altitude chart, expandable params |
| **TLE History** | `/history` | TLE change timeline, expand to compare diffs |
| **Decay Status** | `/decay` | Phase pie chart, periapsis/apoapsis scatter plot, level list |
| **Satellite Detail** | `/satellite/{noradId}` | Full params, periapsis/apoapsis trend chart, history |

**Data flow**: 
```
spacetrack_monitor.py → data/*.jsonl → FastAPI file watcher → WebSocket → Vue 3 SPA (ECharts)
```

---

### Configuration Reference

All configuration is done via `config.yaml`. Fields marked `# web:` can be edited from the Dashboard Settings page (`/settings`) and take effect on the next polling cycle without restart.

```yaml
# HTTP User-Agent for API requests
user_agent: ''

targets:
  norad_ids: [25544]          # web: NORAD IDs to monitor

schedule:
  minute: 17                  # Query minute (Space-Track only, avoid :00/:30)

files:
  data_dir: /data             # Data directory
  data_file: tle_data.jsonl   # Orbital data file
  cache: tle_cache.json       # Breakpoint recovery cache
  run_log: tle_log.jsonl      # Runtime log
  max_log_size_mb: 10         # Log rotation threshold

alerts:
  reentry_warning_km: 200             # web: Periapsis below this → reentry alert
  only_print_on_update: true           # web: Only print on TLE changes
  fallback_maneuver_threshold_km: 5.0  # web: Simple maneuver threshold (km)

retry:
  login_max_failures: 5       # Max Space-Track login retries
  login_pause_seconds: 1800   # Wait after login failure (s)
  request_max_retries: 3      # Max HTTP retries
  request_retry_base: 5       # Exponential backoff base (s)

xpropagator:
  enabled: true                     # web: Enable residual analysis
  host: localhost                    # gRPC host
  port: 50051                        # gRPC port
  maneuver_threshold_km: 5.0         # web: Residual threshold (km)

data_source:
  primary: celestrak            # Primary source (celestrak / spacetrack)
  fallback: spacetrack          # Fallback source (spacetrack / none)
  fallback_threshold: 3                    # web: Fallback after N failures
  celestrak_interval_seconds: 7200         # Polling interval (rate-limit)
  use_supplemental: false                  # Use supplemental GP data
```

### Data Files

The following files are generated automatically:

- **tle_data.jsonl** — Core orbital data recorded on each TLE update, with `change_type` field (initial/correction/maneuver) and rotation protection
- **tle_cache.json** — Temporary cache for breakpoint recovery (Space-Track mode), auto-overwritten
- **tle_log.jsonl** — Runtime logs with rotation protection

> **Log Rotation**: Files exceeding 10MB (configurable) are auto-renamed to `.bak`.

> **Cross-platform Data Directory**:
> - **Linux / Docker**: Defaults to `/data` (configurable via `files.data_dir`)
> - **Windows**: Defaults to project directory. Override via `DATA_DIR` env var or `files.data_dir`
> - **Priority**: `DATA_DIR` env var > `config.yaml` > platform default

---

## Output Examples

### Console Output

```text
2026-04-27 14:12:01 [25544] This batch has 3 solution records, taking the latest one
2026-04-27 14:12:01 [25544] TLE change detected! (hash: abc123 → def456, type: Solution Correction (Correction))

  ===============================================
    ISS (ZARYA)          NORAD 25544
    International Designator: 1998-067A
    Epoch:     2026-04-27T14:08:32
    Perigee:   418.5 km    Apogee: 421.2 km
    Inclination: 51.6400°   Period: 92.870 min
    Eccentricity: 0.0002000   BSTAR: 2.3456e-04
    TLE Hash: abcdef1234567890
  ===============================================  (Perigee +0.3 km, Apogee +0.2 km)
  1 25544U 98067A   ...
  2 25544  51.6400 ...
```

### Seemingly Long Wait Times? (Expected Behavior)

```text
2026-04-25 00:30:13 Next query: 02:12 UTC (in 102 minutes)
```

**Why "102 minutes"?** The script strictly avoids peak hours (:00, :30) and enforces a 60-minute rate limit between requests. When these constraints push past the next scheduled minute, it rolls to the following hour — hence the seemingly long wait. This is expected behavior for API compliance, account safety, and long-term stability.

---

## Orbital Prediction Backend (xpropagator)

### Important Notice

**This repository does not contain or distribute USSF SGP4/SGP4-XP binaries.** TLE-Tracking calls the external xpropagator service via gRPC. See the [xpropagator repository](https://github.com/xpropagation/xpropagator) for deployment.

> The MIT license of this repository applies only to TLE-Tracking's own code. External services, libraries, and propagator components follow their respective license terms.

### Residual Analysis Principle

When a TLE update is detected:

1. Propagate old TLE to new TLE's epoch time
2. Initialize new TLE at new epoch
3. Compute position residual in ECI Cartesian coordinates (km)
4. Residual >= threshold → Maneuver; Residual < threshold → Correction

---

## About Reentry Prediction

The reentry time estimation in this project is extremely rough, for entertainment reference only. It uses BSTAR with a simplified exponential atmospheric model and ignores many critical factors (attitude, solar activity, space weather, etc.).

---

## Data Format (JSONL)

Orbital data is stored as JSON lines in `tle_data.jsonl`. Each record contains: `timestamp`, `change_type`, `norad`, `name`, `periapsis`, `apoapsis`, `epoch`, `tle_hash`, and raw TLE lines.

**change_type values:**
- `initial` — First record
- `correction` — Perigee/apogee change < threshold
- `maneuver` — Perigee/apogee change > threshold
- `decaying` — Periapsis below reentry warning threshold, SGP4 unreliable, skip classification

Threshold configurable via `alerts.fallback_maneuver_threshold_km` (default 5.0 km).

---

## Important Notes

This project strictly complies with Space-Track.org and CelesTrak.org API usage specifications.

### Rate Limits

- **Space-Track**: 1 request/hour to gp endpoints; violations result in account suspension
- **CelesTrak**: Max 1 query per satellite per 2 hours

### Recommended Query Method

**Space-Track** — Use batch query to get all TLEs published in the past hour, then filter locally (see [Space-Track API docs](https://www.space-track.org/documentation#/api) for endpoint details).

**CelesTrak** — Query by NORAD ID, e.g. `https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=json`.

### Scheduling Requirements

- **Space-Track**: Avoid peak hours (:00, :30); use off-peak times (e.g., :12, :48)
- **CelesTrak**: Every 2 hours, script auto-controls frequency

### Do Not Modify Scheduling Logic to Circumvent Rate Limits

---

## Related Links

- [Space-Track.org](https://www.space-track.org/)
- [CelesTrak.org](https://celestrak.org/)
- [Space-Track API Documentation](https://www.space-track.org/documentation#/api)
- [xpropagator](https://github.com/xpropagation/xpropagator)
