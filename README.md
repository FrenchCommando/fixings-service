# fixings-service

Daily stock/index **fixings** (`Open / High / Low / Close / Volume`) served over HTTP, backed by
PostgreSQL. Data comes from [ThetaData](https://www.thetadata.net/) via its native gRPC Python
client, with [yfinance](https://github.com/ranaroussi/yfinance) as a backup source.

This is a modernized fork of [`FrenchCommando/spot-fixings`](https://github.com/FrenchCommando/spot-fixings):
the old ThetaTerminal `.jar` (a local REST hop) has been replaced by the `thetadata` package, which
connects directly over gRPC — no JVM, no `localhost:25503`. See `NOTES.md` for the swap details and
`VISION.md` for goals.

## How it works

- `data_source.py` — fetches EOD bars. `load_thetadata()` uses `ThetaClient.stock_history_eod` /
  `index_history_eod`; `load_yf()` is the yfinance fallback; `load_fixings()` picks between them.
- `data_push.py` — loads fetched bars into Postgres (`update_internal`, `refresh_function`).
- `service.py` — the aiohttp web server (port **5000**). Read endpoints query Postgres; the
  `entry` / `close` endpoints **backfill on demand** — if a row is missing they fetch it from the
  source, insert it, then serve it.
- `db_*.py` — Postgres access (asyncpg). One table, `fixings_table (ticker, date, open, high, low,
  close, volume)`.

## Endpoints

All served from `http://localhost:5000`. Dates are `YYYY-MM-DD`.

| Route | Returns |
|---|---|
| `/` , `/html` | `index.html` UI |
| `/close/{ticker}/{date}` | Close price (backfills if missing) |
| `/entry/{ticker}/{date}` | Full OHLCV row, text (backfills if missing) |
| `/entry_json/{ticker}/{date}` | Full OHLCV row, JSON (backfills if missing) |
| `/ticker/{ticker}` | All rows for a ticker |
| `/date/{date}` | All rows for a date |
| `/tickers` | Distinct tickers in the DB |
| `/dates` | Distinct dates in the DB |
| `/all` | Entire table |
| `/refresh` | Re-fetch the last 364 days for every known ticker |

Indices (`SPX`, `VIX`, `RUT`, `DJX`) come from ThetaData's index endpoint and have `volume = 0`.

## Prerequisites

- **Python 3.13** (deliberate — `thetadata` needs 3.12+; 3.14 not yet trusted for the wheels. See `NOTES.md`).
- **PostgreSQL** running and reachable (developed against 17.x).
- **A ThetaData account.** Access is account-gated even on the free EOD tier; the user here has a
  VALUE subscription. Free EOD history starts June 2023 — older history is the yfinance path's job.

## Setup

**1. Python deps** (into the project venv):

```
.venv\Scripts\python -m pip install -r requirements.txt
```

**2. Secrets** — config comes from the environment, secrets from files under `secrets/` (single
source, no fallbacks; see `.env.example`). Create them:

```
mkdir secrets
copy theta_creds.json.example secrets\theta_creds.json   # then fill in your ThetaData account
echo your-db-password> secrets\db_password               # the Postgres password (any value)
```

**3. Postgres** — create the role and database (use the same password you put in `secrets\db_password`):

```
createuser fixings_user --pwprompt
createdb fixings -O fixings_user
```

The `fixings_table` is created automatically on first startup (idempotent `CREATE TABLE IF NOT
EXISTS`), so there's no manual table step. The service also creates the `fixings` database itself if
it doesn't exist.

> `db_main.py` is a **destructive** dev helper — its `main()` drops and rebuilds the table. Don't run
> it against a populated DB.

> `secrets/` is gitignored — credentials never leave the host. Only the `*.example` templates and the
> env-based loaders (`db_secrets.py`, `data_source.py`, which hold no secrets) are committed.

## Run

Use the launcher — it sets the environment contract and opens a browser:

```
thetaservice.bat
```

(Running `python -m service` directly works too, but only once the env vars from `.env.example` are
set — the launcher does that for you.) Then visit `http://localhost:5000/`. Drop a shortcut to
`thetaservice.bat` in the Windows Startup folder to run it on login.

Quick checks:

```
curl http://localhost:5000/close/AAPL/2024-02-07
curl http://localhost:5000/entry_json/AAPL/2024-02-08
```

## Loading data

- The `entry` / `close` endpoints backfill a single missing `(ticker, date)` on demand.
- `/refresh` re-fetches the last 364 days for **every ticker already in the table** (so a fresh DB
  refreshes nothing until tickers exist — hit a few `entry` URLs first to seed them).
- `data_push.py` can be run directly to bulk-load a ticker over a date range.

## Deployment

- **Local (Windows)** — `thetaservice.bat`, Postgres as a local service.
- **GitHub Pages** — off the table for real data (licensing). At most a static demo against synthetic data.
- **Self-hosted (Raspberry Pi) via Docker** — the intended target. `Dockerfile` + `compose.yml` make
  the service an app behind the [`proxy-auth`](../proxy-auth) Authelia/nginx stack (it joins the
  external `proxy` network like `sample-app`; Authelia provides auth, so the service has none of its
  own). On the Pi:

  ```sh
  mkdir -p secrets
  echo "$(openssl rand -hex 24)" > secrets/db_password        # generated on the Pi, never committed
  cp theta_creds.json.example secrets/theta_creds.json        # then fill in your ThetaData account
  chmod 600 secrets/*
  docker compose up -d --build                                # native arm64 build on the Pi
  ```

  Then wire it into the auth stack: copy `deploy/nginx/fixings.conf` into the auth stack's `conf.d/`
  (set the `server_name`) and add an Authelia `access_control` rule (`fixings.<domain> → two_factor`).
  The `fixings` data is **re-derivable** (re-fetch via `/entry` hits or `/refresh`), so the `db-data`
  volume is the only state and the Pi stays disposable.

  **Full runbook:** [`deploy/SETUP.md`](deploy/SETUP.md) — from-zero steps, secret generation, auth
  wiring, edge TLS, seeding.

## Files

| File | Purpose |
|---|---|
| `service.py` | aiohttp web server + routes |
| `data_source.py` | ThetaData (gRPC) + yfinance fetchers |
| `data_push.py` | load/refresh data into Postgres |
| `db_*.py` | Postgres schema and access |
| `index.html` | minimal UI |
| `thetaservice.bat` | local launcher (sets env, runs service, opens browser) |
| `Dockerfile` / `compose.yml` | container image + app+db stack for the Pi |
| `deploy/nginx/fixings.conf` | nginx server block to copy into the proxy-auth stack |
| `.env.example` / `theta_creds.json.example` | env contract + creds template |
| `secrets/` | `db_password` + `theta_creds.json` (gitignored) |
| `NOTES.md` / `VISION.md` | design decisions / goals |
