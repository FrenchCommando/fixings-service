import datetime as dt
import json
import os
from decimal import Decimal

from aiohttp import web

from data_source import NoDataFoundError
from data_push import update_internal, refresh_function
from service_constants import port_number
from db_def import fixings_table_name
from db_stuff import get_ticker, get_date, get_entry, get_all, get_entry_attribute, get_list, build_table
from db_main import get_pool


base_dir = os.path.abspath(os.path.dirname(__file__))


def rep_line_format(rep0):
    keys_format = dict(open=".2f", low=".2f", high=".2f", close=".2f", volume="")
    return ",\t".join(f"{u}:\t{v:{keys_format.get(u, "")}}" for u, v in rep0.items())


def rep_to_txt(rep):
    rep_text = "\n".join([str(len(rep)), "\n".join(rep_line_format(rep0=rep0) for rep0 in rep)])
    return rep_text


async def handle_ticker(request):
    pool = request.app['pool']
    ticker_value = request.match_info.get('ticker', '')
    async with pool.acquire() as connection:
        rep = await get_ticker(conn=connection, table_name=fixings_table_name, ticker=ticker_value)
        rep_text = rep_to_txt(rep=rep)
        return web.Response(text=rep_text)


async def handle_date(request):
    pool = request.app['pool']
    date_str = request.match_info.get('date', '')
    date_value = dt.datetime.strptime(date_str, '%Y-%m-%d').date()
    # print(date_value, type(date_value))
    async with pool.acquire() as connection:
        rep = await get_date(conn=connection, table_name=fixings_table_name, date=date_value)
        rep_text = rep_to_txt(rep=rep)
        return web.Response(text=rep_text)


async def handle_entry(request):
    pool = request.app['pool']
    ticker_value = request.match_info.get('ticker', '')
    date_str = request.match_info.get('date', '')
    date_value = dt.datetime.strptime(date_str, '%Y-%m-%d').date()
    async with pool.acquire() as connection:
        rep = await get_entry(conn=connection, table_name=fixings_table_name, ticker=ticker_value, date=date_value)
        if len(rep) == 0:
            try:
                await update_internal(conn=connection, ticker=ticker_value, date_from=date_value, date_to=date_value)
            except NoDataFoundError as e:
                return web.Response(text=f"No entry found {e}")
            rep = await get_entry(
                conn=connection, table_name=fixings_table_name, ticker=ticker_value, date=date_value,
            )
            if len(rep) == 0:
                return web.Response(text="No entry found")
        # rep_text = "\n".join([str(len(rep)), "\n".join(str(u) for u in rep)])
        rep_text_entry = "\n".join(f"{u}:\t{v}" for u, v in rep[0].items())
        return web.Response(text=rep_text_entry)


class BackUpEncoder(json.JSONEncoder):
    def default(self, obj):
        if type(obj) is dt.date:
            return str(obj)
        if type(obj) is Decimal:
            return float(obj)
        # try:
        #     return super().default(obj)
        # except TypeError as e:
        #     print(e)
        #     return str(obj)
        return super().default(obj)


async def handle_entry_json(request):
    pool = request.app['pool']
    ticker_value = request.match_info.get('ticker', '')
    date_str = request.match_info.get('date', '')
    date_value = dt.datetime.strptime(date_str, '%Y-%m-%d').date()
    async with pool.acquire() as connection:
        rep = await get_entry(conn=connection, table_name=fixings_table_name, ticker=ticker_value, date=date_value)
        if len(rep) == 0:
            try:
                await update_internal(conn=connection, ticker=ticker_value, date_from=date_value, date_to=date_value)
            except NoDataFoundError as e:
                return web.Response(text=f"No entry found {e}")
            rep = await get_entry(
                conn=connection, table_name=fixings_table_name, ticker=ticker_value, date=date_value,
            )
            if len(rep) == 0:
                return web.Response(text="No entry found")
        # rep_text = "\n".join([str(len(rep)), "\n".join(str(u) for u in rep)])
        rep_entry_json = json.dumps(dict(rep[0].items()), cls=BackUpEncoder)
        return web.Response(text=rep_entry_json)


async def handle_entry_close(request):
    pool = request.app['pool']
    ticker_value = request.match_info.get('ticker', '')
    date_str = request.match_info.get('date', '')
    date_value = dt.datetime.strptime(date_str, '%Y-%m-%d').date()
    async with pool.acquire() as connection:
        rep = await get_entry_attribute(
            conn=connection, table_name=fixings_table_name, ticker=ticker_value, date=date_value, attribute='close',
        )
        if len(rep) == 0:
            try:
                await update_internal(conn=connection, ticker=ticker_value, date_from=date_value, date_to=date_value)
            except NoDataFoundError as e:
                return web.Response(text=f"No entry found {e}")
            rep = await get_entry_attribute(
                conn=connection, table_name=fixings_table_name, ticker=ticker_value, date=date_value, attribute='close',
            )
            if len(rep) == 0:
                return web.Response(text="No entry found")
        # rep_text = "\n".join([str(len(rep)), "\n".join(str(u) for u in rep)])
        rep_value = f"{rep[0]['close']:.2f}"
        return web.Response(text=rep_value)


async def handle_refresh(request):
    pool = request.app['pool']
    async with pool.acquire() as connection:
        res = await refresh_function(conn=connection)
        rep_text = "\n".join([str(len(res)), "\n".join(str(u) for u in res)])
        return web.Response(text=rep_text)


async def handle_all_tickers(request):
    pool = request.app['pool']
    async with pool.acquire() as connection:
        rep = await get_list(conn=connection, table_name=fixings_table_name, column_str='ticker')
        rep_text = "\n".join([str(len(rep)), "\n".join(str(u) for u in sorted(v['ticker'] for v in rep))])
        return web.Response(text=rep_text)


async def handle_all_dates(request):
    pool = request.app['pool']
    async with pool.acquire() as connection:
        rep = await get_list(conn=connection, table_name=fixings_table_name, column_str='date')
        rep_text = "\n".join([str(len(rep)), "\n".join(str(u) for u in sorted(v['date'] for v in rep))])
        return web.Response(text=rep_text)


async def handle_all(request):
    pool = request.app['pool']
    async with pool.acquire() as connection:
        rep = await get_all(conn=connection, table_name=fixings_table_name)
        rep_text = "\n".join([str(len(rep)), "\n".join(str(u) for u in rep)])
        return web.Response(text=rep_text)


async def index_handler(request):
    try:
        with open(os.path.join(base_dir, 'index.html'), 'r') as f:
            html_content = f.read()
        return web.Response(text=html_content, content_type='text/html')
    except FileNotFoundError:
        return web.Response(text="<h1>404: Not Found</h1>", status=404, content_type='text/html')


async def create_db_pool(app_inst):
    pool = await get_pool()
    # Idempotent: CREATE TABLE IF NOT EXISTS, so a fresh DB is usable on first run.
    async with pool.acquire() as conn:
        await build_table(conn=conn, table_name=fixings_table_name)
    app_inst['pool'] = pool

async def close_db_pool(app_inst):
    # Close the connection pool when the application shuts down.
    # asyncpg's Pool.close() is itself a coroutine (and there is no wait_closed()).
    await app_inst['pool'].close()


def init_app():
    app_inst = web.Application()
    app_inst.on_startup.append(create_db_pool)
    app_inst.on_cleanup.append(close_db_pool)
    app_inst.router.add_route('GET', '/close/{ticker}/{date}', handle_entry_close)
    app_inst.router.add_route('GET', '/entry/{ticker}/{date}', handle_entry)
    app_inst.router.add_route('GET', '/entry_json/{ticker}/{date}', handle_entry_json)
    app_inst.router.add_route('GET', '/ticker/{ticker}', handle_ticker)
    app_inst.router.add_route('GET', '/date/{date}', handle_date)
    app_inst.router.add_route('GET', '/refresh', handle_refresh)
    app_inst.router.add_route('GET', '/all', handle_all)
    app_inst.router.add_route('GET', '/tickers', handle_all_tickers)
    app_inst.router.add_route('GET', '/dates', handle_all_dates)
    app_inst.router.add_route('GET', '/html', index_handler)
    app_inst.router.add_route('GET', '/', index_handler)
    return app_inst


if __name__ == "__main__":
    app = init_app()
    web.run_app(app, port=port_number)

    # http://localhost:5000/ticker/SPY
    # http://localhost:5000/date/2025-08-08
    # http://localhost:5000/entry/SPY/2025-08-08
    # http://localhost:5000/entry_json/SPY/2025-08-08
    # http://localhost:5000/close/SPY/2025-08-08
