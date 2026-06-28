# NOTES

Non-obvious decisions and state for the fixings-service modernization. See `VISION.md` for goals.

## Origin
Modernizing the upstream repo `FrenchCommando/spot-fixings` (cloned at `~/spot-fixings`):
swap the ThetaTerminal JAR for ThetaData's native Python package, keep yfinance as a backup.

## Environment
- **`.venv` uses Python 3.13**, not the system-default 3.14. Reason: `thetadata` needs 3.12+,
  upstream ran 3.13, and 3.14 is too new to trust for `asyncpg`/`yfinance` wheels. Don't "upgrade"
  to 3.14 without checking wheel availability first.
- **`python-dotenv` is in `requirements.txt` as an explicit entry** even though our own code never
  imports it. Reason: `thetadata 1.0.9` has a packaging bug — its `client.py` does `from dotenv import
  load_dotenv` but the wheel fails to declare `python-dotenv` as a dependency, so a fresh install
  raises `ModuleNotFoundError: No module named 'dotenv'` on `import thetadata`. Revisit (and possibly
  drop our entry) if a newer `thetadata` release fixes its metadata.
- `requirements.txt` is intentionally unpinned (current stable). `httpx` was **dropped** when the
  swap was applied — nothing imports it anymore (the native client raises `NoDataFoundError`, not
  `httpx.HTTPStatusError`).

## Licensing — load-bearing constraint
ThetaData is account-gated even on the free tier; the data is licensed, not public-domain. Therefore
**the real fixings can never be redistributed publicly** → public GitHub Pages is OFF the table.
Target deployment is personal/self-hosted (Raspberry Pi + Docker + nginx), credentials server-side.
GitHub Pages could at most host a demo with synthetic/sample data. `.gitignore` keeps `secrets/` (the
`db_password` + `theta_creds.json` files) and `.venv` out of any repo; the `*.example` templates and
the env-based loaders (`db_secrets.py`, `data_source.py`, which hold no secrets) are committed.

## Config & secrets — single source, no fallbacks
All config comes from the environment (`PG_HOST`, `PG_PORT`, `PG_DATABASE`, `POSTGRES_USER`); secrets
come from files (`POSTGRES_PASSWORD_FILE`, `THETADATA_CREDS_FILE`). No JSON-vs-env fallback — exactly
one source per value, so there's nothing ambiguous to debug and no stale copy to leak. The DB password
is read from the *same* file the postgres container uses (`/run/secrets/db_password`), so it isn't
duplicated. `thetaservice.bat` sets these for local runs; `compose.yml` sets them for the container —
identical contract. See `.env.example`.

User has a VALUE-level subscription (for options), so credentials are a non-issue for them.

## The JAR swap — APPLIED (2026-06-28)
The entire JAR coupling was ONE function: `data_source.py::load_thetadata()`, which used to do an
httpx GET to `http://localhost:25503/v3/...` (the REST server the JAR exposed). Everything else
reaches data through `load_fixings()`, which already abstracts the source cleanly.

Done:
- `load_thetadata()` now uses `ThetaClient().stock_history_eod(...)` / `index_history_eod(...)`
  (native gRPC, no JVM, no localhost). Client is a lazily-built module singleton (it authenticates
  on construction, so we build it once).
- `runthetadata.bat` / `runthetadata3.bat` not carried over (no JAR to launch). `thetaservice.bat`
  rewritten to just start the service + browser.
- **3 `except httpx.HTTPStatusError` clauses in `service.py`** (handle_entry, handle_entry_json,
  handle_entry_close) retargeted to `except NoDataFoundError` (re-exported from `data_source`).
  This was the only place the swap leaked beyond `data_source.py`.
- Creds: `data_source._get_client()` reads the JSON at `$THETADATA_CREDS_FILE` (`{"email","password"}`)
  and passes them to `ThetaClient(email=, password=)` — chosen over the JAR's line-based `secrets.txt`.
  Lazy (only built on first fetch), so DB-only requests don't need ThetaData creds. Locally the file is
  `secrets/theta_creds.json`; in the container it's the mounted `theta_creds` secret.

### Column mapping — CONFIRMED against the VALUE account
`stock_history_eod` / `index_history_eod` return a pandas frame with lowercase columns:
`created, last_trade, open, high, low, close, volume, count, bid_size, ...` (16 cols).
- `created` is a **tz-aware (America/New_York) datetime**, NOT the old JAR's string — use
  `row.created.date()` for `Date` (no more `strptime` parsing).
- `open/high/low/close` are float64, `volume` is int64 → cast to `float()`/`int()` for asyncpg
  (it then stores them as Decimal/BIGINT fine).
- Indices DO return a `volume` column, but it's `0` (not absent). No special-casing needed.
- No-data dates (weekends, future, pre-June-2023 on free tier) raise `thetadata.errors.NoDataFoundError`.

### Verified end-to-end (2026-06-28)
`python data_source.py` fetches; the service serves `/close /entry /entry_json` from Postgres 17.6
(`fixings` DB, already populated); a DB miss on a valid trading day backfills via native fetch +
insert; a miss on a non-trading day returns "No entry found" via the `NoDataFoundError` path.

### Server constraints that carry over (not JAR-specific)
- Max 365 days per request (`refresh_function` already uses 364 — fine).
- "EOD not available for the current day" (`refresh_function` already uses today-1 — fine).
- Free tier EOD history only goes back to **June 2023**; older history is the yfinance path's job.
