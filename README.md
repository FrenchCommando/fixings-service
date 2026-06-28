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

**2. ThetaData credentials** — create `creds.txt` in the project root, email on line 1, password on
line 2:

```
you@example.com
your-password
```

`data_source.py` looks for credentials in this order: `$THETADATA_CREDENTIALS_FILE`, then project
`creds.txt`, then the legacy `~/ThetaData/secrets.txt` (same format).

**3. Postgres** — create the role and database:

```
createuser fixings_user --pwprompt        # password: fixings_pass (or your own)
createdb fixings -O fixings_user
```

Put the matching credentials in `db_secrets.json`:

```json
{ "user": "fixings_user", "password": "fixings_pass" }
```

The `fixings_table` is created automatically on first startup (idempotent `CREATE TABLE IF NOT
EXISTS`), so there's no manual table step. The service also creates the `fixings` database itself if
it doesn't exist.

> `db_main.py` is a **destructive** dev helper — its `main()` drops and rebuilds the table. Don't run
> it against a populated DB.

> `creds.txt` and `db_secrets.json` are gitignored — credentials never leave the host. `db_secrets.py`
> is committed (it's a generic loader with no secrets in it).

## Run

```
.venv\Scripts\python -m service
```

or use the launcher, which starts the service and opens a browser:

```
thetaservice.bat
```

Then visit `http://localhost:5000/`. Drop a shortcut to `thetaservice.bat` in the Windows Startup
folder to run it on login.

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

- **Local (Windows)** — the supported path today: `thetaservice.bat`, Postgres as a local service.
- **Self-hosted (Raspberry Pi)** — the intended target. Because the data is **licensed and cannot be
  redistributed**, it must stay server-side: Postgres + this service behind an **nginx** reverse
  proxy (TLS, and basic-auth since the service has no auth of its own and aiohttp binds all
  interfaces). Credentials live on the Pi, never in the repo.
- **GitHub Pages** — off the table for real data (licensing). At most a static demo against synthetic data.
- **Docker / docker-compose** — _planned, not yet written._ Would bundle the service with Postgres;
  needs the DB host/credentials made env-configurable first.

## Files

| File | Purpose |
|---|---|
| `service.py` | aiohttp web server + routes |
| `data_source.py` | ThetaData (gRPC) + yfinance fetchers |
| `data_push.py` | load/refresh data into Postgres |
| `db_*.py` | Postgres schema and access |
| `index.html` | minimal UI |
| `thetaservice.bat` | launcher (service + browser) |
| `creds.txt` / `db_secrets.json` | credentials (gitignored) |
| `NOTES.md` / `VISION.md` | design decisions / goals |
