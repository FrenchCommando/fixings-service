from db_constants import fixings_table_name, error_table_name


table_to_specs = {
    fixings_table_name:
        "ticker TEXT, "
        "date DATE NOT NULL, "
        "open NUMERIC(9, 2), "
        "high NUMERIC(9, 2), "
        "low NUMERIC(9, 2), "
        "close NUMERIC(9, 2), "
        "volume BIGINT,"
        "PRIMARY KEY (ticker, date)",
    error_table_name:
        "id serial PRIMARY KEY, "
        "message TEXT",
}
