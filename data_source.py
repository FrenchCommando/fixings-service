import datetime as dt
import os
from pathlib import Path

import yfinance as yf
from thetadata import ThetaClient
from thetadata.errors import NoDataFoundError  # re-exported so service.py can catch it

# These indices have no per-share volume; ThetaData serves them on a separate endpoint.
INDEX_SYMBOLS = {"SPX", "VIX", "RUT", "DJX"}

# Candidate credential locations, in priority order. The native client wants a file with
# the email on line 1 and the password on line 2 -- the same format the old ThetaTerminal
# JAR used for its secrets.txt, so the legacy file works as a fallback.
_CREDS_CANDIDATES = (
    os.getenv("THETADATA_CREDENTIALS_FILE"),
    Path(__file__).resolve().parent / "creds.txt",
    Path.home() / "ThetaData" / "secrets.txt",
)

_client = None  # ThetaClient authenticates on construction, so build it once and reuse.


def _creds_file():
    for candidate in _CREDS_CANDIDATES:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise FileNotFoundError(
        "No ThetaData credentials found. Set THETADATA_CREDENTIALS_FILE, or create "
        "creds.txt (email on line 1, password on line 2) in the project directory."
    )


def _get_client():
    global _client
    if _client is None:
        _client = ThetaClient(creds_file=_creds_file(), dataframe_type="pandas")
    return _client


def load_thetadata(ticker, date_from, date_to):
    client = _get_client()
    if ticker in INDEX_SYMBOLS:
        frame = client.index_history_eod(symbol=ticker, start_date=date_from, end_date=date_to)
    else:
        frame = client.stock_history_eod(symbol=ticker, start_date=date_from, end_date=date_to)

    out_data = []
    for row in frame.itertuples(index=False):
        # `created` is a tz-aware (America/New_York) timestamp of the EOD record; its date is
        # the trade date. Native column labels are lowercase, unlike the DB dict keys.
        out_data.append(dict(
            Date=row.created.date(),
            Open=float(row.open), High=float(row.high), Low=float(row.low), Close=float(row.close),
            Volume=int(row.volume),
        ))
    return out_data


yf_mapping = dict(
    NDX="^NDX",
)  # mapping means override - don't add SPX


def load_yf(ticker, date_from, date_to):
    yf_ticker = yf_mapping.get(ticker, ticker)
    ticker_obj = yf.Ticker(yf_ticker)
    historical_data = ticker_obj.history(start=date_from, end=date_to + dt.timedelta(days=1))
    out_data = []
    for line in historical_data.iterrows():
        d_date, d_line = line
        d = dict(
            Date=d_date.date(),
            Open=d_line["Open"], High=d_line["High"], Low=d_line["Low"], Close=d_line["Close"],
            Volume=d_line["Volume"],
        )
        out_data.append(d)

    return out_data


def load_fixings(ticker, date_from, date_to):
    if ticker in yf_mapping:
        return load_yf(ticker=ticker, date_from=date_from, date_to=date_to)
    else:
        return load_thetadata(ticker=ticker, date_from=date_from, date_to=date_to)


def main():
    ticker_main = "SPX"
    start_date = dt.date(2024, 2, 7)
    end_date = dt.date(2024, 2, 9)
    out_main = load_thetadata(ticker=ticker_main, date_from=start_date, date_to=end_date)
    out_main_yf = load_yf(ticker=ticker_main, date_from=start_date, date_to=end_date)
    out_main0 = load_fixings(ticker=ticker_main, date_from=start_date, date_to=end_date)
    print(out_main)
    print(out_main_yf)
    print(out_main0)

    # Server constraints carried over from the JAR era:
    #   "Too many days between start and end date; max 365 days allowed"
    #   "EOD is not available for the current day"
    # Free EOD tier history starts June 2023; older history is the yfinance path's job.


if __name__ == '__main__':
    main()
