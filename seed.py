"""Bootstrap an empty `fixings` DB with a year of history for a starting ticker set.

`/refresh` only re-fetches tickers already in the table, so on a fresh DB it does nothing —
there is no ticker to refresh until one is introduced. This script closes that gap: it reads
the symbols in `seed_tickers.txt` and, for each, fetches the last 364 days (the same window
`refresh_function` uses) and inserts them. That both registers the ticker and fills its history
in one pass, after which `/refresh` keeps everything current.

Run it once after the stack is up:

    # locally (env from .env.example / thetaservice.bat):
    .venv\\Scripts\\python -m seed
    # on the Pi (env already set inside the container):
    docker compose exec app python -m seed

Idempotent: re-running skips rows that already exist (unique (ticker, date)), so it is safe to
re-run after editing `seed_tickers.txt`. Needs ThetaData creds (THETADATA_CREDS_FILE) since it
fetches from the source. A symbol with no data in the window (bad ticker, non-trading window)
is logged and skipped without aborting the rest.
"""
import asyncio
import datetime as dt
import os

from data_source import NoDataFoundError
from data_push import update_internal
from db_constants import fixings_database, fixings_table_name
from db_stuff import connect_to_database, build_table

base_dir = os.path.abspath(os.path.dirname(__file__))
seed_tickers_file = os.path.join(base_dir, "seed_tickers.txt")


def read_seed_tickers(path=seed_tickers_file):
    with open(path, "r") as handle:
        lines = (line.strip() for line in handle)
        return [line for line in lines if line and not line.startswith("#")]


async def seed(date_from=None, date_to=None):
    if date_to is None:
        date_to = dt.date.today() - dt.timedelta(days=1)   # EOD isn't available for the current day
    if date_from is None:
        date_from = date_to - dt.timedelta(days=364)       # max 365 days per source request

    tickers = read_seed_tickers()
    print(f"Seeding {len(tickers)} tickers from {date_from} to {date_to}")
    pool = await connect_to_database(database=fixings_database)
    try:
        async with pool.acquire() as conn:
            await build_table(conn=conn, table_name=fixings_table_name)   # idempotent; fresh DB safe
        for ticker in tickers:
            print(f"--- {ticker} ---")
            async with pool.acquire() as conn:
                try:
                    await update_internal(
                        conn=conn, ticker=ticker, date_from=date_from, date_to=date_to,
                    )
                except NoDataFoundError as error:
                    print(f"no data for {ticker}: {error}")
    finally:
        await pool.close()


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(seed())
