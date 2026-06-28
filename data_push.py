import datetime as dt
import asyncio
import asyncpg
from data_source import load_fixings
from db_constants import fixings_table_name, fixings_database
from db_stuff import connect_to_database, insert_entry, get_ticker, get_list


async def update_internal(conn, ticker, date_from, date_to):
    out_data = load_fixings(ticker=ticker, date_from=date_from, date_to=date_to)
    for line in out_data:
        print(line)
        try:
            entry_out = await insert_entry(conn=conn, table_name=fixings_table_name, ticker=ticker, **line)
            print(entry_out)
        except asyncpg.exceptions.UniqueViolationError as e:
            print(e)


async def update(ticker, date_from, date_to):
    pool = await connect_to_database(database=fixings_database)
    try:
        async with pool.acquire() as conn:
            await update_internal(conn=conn, ticker=ticker, date_from=date_from, date_to=date_to)
    finally:
        await pool.close()


async def show_ticker(ticker):
    pool = await connect_to_database(database=fixings_database)
    try:
        async with pool.acquire() as conn:
            out_ticker = await get_ticker(conn=conn, table_name=fixings_table_name, ticker=ticker)
            print(out_ticker)
    finally:
        await pool.close()


async def refresh_function(conn: asyncpg.Connection):
    date_to = dt.date.today() - dt.timedelta(days=1)
    date_from = date_to - dt.timedelta(days=364)
    res = []
    rep = await get_list(conn=conn, table_name=fixings_table_name, column_str='ticker')
    for r_item in rep:
        r_ticker = r_item['ticker']
        await update_internal(conn=conn, ticker=r_ticker, date_from=date_from, date_to=date_to)
        res.append(r_item)
    return res


async def update_all():
    pool = await connect_to_database(database=fixings_database)
    try:
        async with pool.acquire() as conn:
            await refresh_function(conn=conn)
    finally:
        await pool.close()



if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    run_one = True
    if run_one:
        ticker_main = "AAPL"
        loop.run_until_complete(show_ticker(ticker=ticker_main))
        start = dt.date(2024, 9, 1)
        end = dt.date(2025, 8, 22)
        loop.run_until_complete(update(ticker=ticker_main, date_from=start, date_to=end))
        loop.run_until_complete(show_ticker(ticker=ticker_main))
    else:
        loop.run_until_complete(update_all())
