import os

fixings_database = os.environ["PG_DATABASE"]

fixings_table_name = "fixings_table"
error_table_name = "error_table"  # maybe unused

host = os.environ["PG_HOST"]            # "fixings-service-db" in compose, "localhost" locally
pg_port_number = int(os.environ["PG_PORT"])
