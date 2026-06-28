import asyncpg
import datetime as dt
from db_constants import host, pg_port_number
from db_secrets import postgres_user, postgres_password
from db_def import table_to_specs


async def connect_to_database(database: str):
    try:
        pool = await asyncpg.create_pool(
            dsn=f"postgresql://{postgres_user}:{postgres_password}@{host}:{pg_port_number}/{database}",
        )
    except asyncpg.InvalidCatalogNameError:
        sys_conn = await asyncpg.connect(
            dsn=f"postgresql://{postgres_user}:{postgres_password}@{host}:{pg_port_number}"
        )
        await sys_conn.execute(
            f'CREATE DATABASE "{database}" OWNER "{postgres_user}";'
        )
        await sys_conn.close()
        pool = await asyncpg.create_pool(
            dsn=f"postgresql://{postgres_user}:{postgres_password}@{host}:{pg_port_number}/{database}",
        )
    return pool


async def build_table(conn: asyncpg.Connection, table_name: str):
    await conn.execute(f'CREATE TABLE IF NOT EXISTS {table_name}({table_to_specs[table_name]});')


async def truncate_table(conn: asyncpg.Connection, table_name: str):
    await conn.execute(f'TRUNCATE {table_name};')


async def drop_table(conn: asyncpg.Connection, table_name: str):
    await conn.execute(f'DROP TABLE IF EXISTS {table_name};')


async def insert_entry(conn: asyncpg.Connection, table_name: str, **kwargs):
    await conn.execute(f'''
        INSERT INTO {table_name}({",".join(kwargs.keys())})
        VALUES({",".join(f"${i+1}" for i in range(len(kwargs.keys())))});
    ''', *kwargs.values())
    return "All good"


async def get_all(conn: asyncpg.Connection, table_name: str):
    return await conn.fetch(f'SELECT * FROM {table_name};')


async def get_ticker(conn: asyncpg.Connection, table_name: str, ticker: str):
    return await conn.fetch(f'SELECT * FROM {table_name} WHERE ticker = $1;', ticker)


async def get_date(conn: asyncpg.Connection, table_name: str, date: dt.date):
    return await conn.fetch(f'SELECT * FROM {table_name} WHERE date = $1;', date)


async def get_entry(conn: asyncpg.Connection, table_name: str, ticker: str, date: dt.date):
    return await conn.fetch(
        f'SELECT * FROM {table_name} WHERE ticker = $1 AND date = $2;', ticker, date,
    )


async def get_list(conn: asyncpg.Connection, table_name: str, column_str: str):
    # DISTINCT for unique keys
    return await conn.fetch(f'SELECT DISTINCT {column_str} FROM {table_name};')


async def get_entry_attribute(conn: asyncpg.Connection, table_name: str, ticker: str, date: dt.date, attribute: str):
    return await conn.fetch(
        f'SELECT {attribute} FROM {table_name} WHERE ticker = $1 AND date = $2;', ticker, date,
    )


async def read_db(conn: asyncpg.Connection, table_name: str, len_only: bool = False, head: int = 0):
    row = await get_all(conn=conn, table_name=table_name)
    if not len_only:
        for i, u in enumerate(row):
            print(i, u)
            if head and i >= head:
                break
    print(f"\t\tSize of db {table_name}:\t{len(row)}")
