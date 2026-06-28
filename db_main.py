import asyncio
from db_constants import fixings_table_name, fixings_database
from db_stuff import connect_to_database, truncate_table, build_table, get_all, drop_table


async def get_pool():
    return await connect_to_database(database=fixings_database)


async def clear_fixings_table(drop=False):
    pool = await connect_to_database(database=fixings_database)
    try:
        async with pool.acquire() as conn:
            await build_table(conn=conn, table_name=fixings_table_name)
        async with pool.acquire() as conn:
            if drop:
                await drop_table(conn=conn, table_name=fixings_table_name)  # drop if changing definition
            else:
                await truncate_table(conn=conn, table_name=fixings_table_name)
            await build_table(conn=conn, table_name=fixings_table_name)
    finally:
        await pool.close()

async def get_all_main():
    pool = await connect_to_database(database=fixings_database)
    try:
        async with pool.acquire() as conn:
            out = await get_all(conn=conn, table_name=fixings_table_name)
            print(out)
    finally:
        await pool.close()


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(get_all_main())
    loop.run_until_complete(clear_fixings_table(drop=True))
    loop.run_until_complete(get_all_main())


if __name__ == '__main__':
    main()
