"""Pin the behaviour we depend on from the `thetadata` library and from `data_source`.

Two layers:

* **Unit** (no network) — our own routing logic in `load_fixings`.
* **Integration** (real ThetaData calls, skipped without creds) — the contract that actually
  drifts: column names, dtypes, the dict shape `data_push`/`db_stuff` insert, the volume=0 quirk
  for indices, and `NoDataFoundError` on no-data dates (which `service.py` catches). If a future
  `thetadata` release changes any of these, these tests fail loudly instead of the DB insert
  silently breaking.

Run from the repo root:  .venv\\Scripts\\python -m unittest discover -s tests
"""
import datetime as dt
import os
import sys
import unittest
from unittest import mock

# Make `import data_source` work regardless of the cwd the tests are launched from.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# data_source reads creds from $THETADATA_CREDS_FILE (lazily). Default it to the local secret so
# the integration tests can run; skip them if the file isn't there.
_DEFAULT_CREDS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "secrets", "theta_creds.json"))
os.environ.setdefault("THETADATA_CREDS_FILE", _DEFAULT_CREDS)
_HAVE_CREDS = os.path.isfile(os.environ["THETADATA_CREDS_FILE"])

import data_source  # noqa: E402  (after sys.path / env setup)
from thetadata.errors import NoDataFoundError  # noqa: E402

requires_creds = unittest.skipUnless(_HAVE_CREDS, "ThetaData creds not available")

# Stable historical session (a Wednesday) and a guaranteed no-data day (the following Saturday).
TRADING_DAY = dt.date(2024, 2, 7)
NON_TRADING_DAY = dt.date(2024, 2, 10)

DICT_KEYS = {"Date", "Open", "High", "Low", "Close", "Volume"}
# Columns of the native frame that load_thetadata() reads — the schema-drift tripwire.
RAW_COLUMNS_USED = {"created", "open", "high", "low", "close", "volume"}


class RoutingTests(unittest.TestCase):
    """No network: pin how load_fixings dispatches between sources."""

    def test_index_symbols_set(self):
        self.assertEqual(data_source.INDEX_SYMBOLS, {"SPX", "VIX", "RUT", "DJX"})

    def test_yf_mapping(self):
        # NDX is the one symbol we override to yfinance; SPX must NOT be mapped.
        self.assertEqual(data_source.yf_mapping.get("NDX"), "^NDX")
        self.assertNotIn("SPX", data_source.yf_mapping)

    def test_mapped_ticker_uses_yfinance(self):
        with mock.patch.object(data_source, "load_yf", return_value=["yf"]) as yf, \
             mock.patch.object(data_source, "load_thetadata", return_value=["theta"]) as theta:
            out = data_source.load_fixings("NDX", TRADING_DAY, TRADING_DAY)
        self.assertEqual(out, ["yf"])
        yf.assert_called_once()
        theta.assert_not_called()

    def test_unmapped_ticker_uses_thetadata(self):
        with mock.patch.object(data_source, "load_yf", return_value=["yf"]) as yf, \
             mock.patch.object(data_source, "load_thetadata", return_value=["theta"]) as theta:
            out = data_source.load_fixings("AAPL", TRADING_DAY, TRADING_DAY)
        self.assertEqual(out, ["theta"])
        theta.assert_called_once()
        yf.assert_not_called()


@requires_creds
class ThetaRawFrameContract(unittest.TestCase):
    """The direct schema tripwire: pin the raw ThetaClient frame columns and dtypes."""

    def test_stock_frame_columns_and_dtypes(self):
        frame = data_source._get_client().stock_history_eod(
            symbol="AAPL", start_date=TRADING_DAY, end_date=TRADING_DAY,
        )
        self.assertTrue(RAW_COLUMNS_USED.issubset(set(frame.columns)),
                        msg=f"missing columns: {RAW_COLUMNS_USED - set(frame.columns)}")
        # `created` must stay a tz-aware datetime (load_thetadata calls .date() on it).
        created_dtype = str(frame["created"].dtype)
        self.assertTrue(created_dtype.startswith("datetime64"), created_dtype)
        self.assertIsNotNone(getattr(frame["created"].dtype, "tz", None), "created lost its timezone")
        for col in ("open", "high", "low", "close"):
            self.assertEqual(frame[col].dtype.kind, "f", f"{col} is no longer float")
        self.assertIn(frame["volume"].dtype.kind, ("i", "u"), "volume is no longer integer")


@requires_creds
class LoadThetadataContract(unittest.TestCase):
    """Pin load_thetadata's output — the dicts that get inserted into Postgres."""

    @classmethod
    def setUpClass(cls):
        cls.stock = data_source.load_thetadata("AAPL", TRADING_DAY, TRADING_DAY)
        cls.index = data_source.load_thetadata("SPX", TRADING_DAY, TRADING_DAY)

    def test_returns_one_row(self):
        self.assertEqual(len(self.stock), 1)
        self.assertEqual(len(self.index), 1)

    def test_dict_keys_exact(self):
        self.assertEqual(set(self.stock[0]), DICT_KEYS)
        self.assertEqual(set(self.index[0]), DICT_KEYS)

    def test_value_types(self):
        row = self.stock[0]
        self.assertIsInstance(row["Date"], dt.date)
        for col in ("Open", "High", "Low", "Close"):
            self.assertIsInstance(row[col], float)
        self.assertIsInstance(row["Volume"], int)

    def test_date_matches_request(self):
        self.assertEqual(self.stock[0]["Date"], TRADING_DAY)

    def test_ohlc_sane(self):
        row = self.stock[0]
        self.assertLessEqual(row["Low"], row["High"])
        self.assertTrue(row["Low"] <= row["Open"] <= row["High"])
        self.assertTrue(row["Low"] <= row["Close"] <= row["High"])
        # Loose range guards the price-decoding scale (catches a factor/units regression),
        # without asserting an exact value that ThetaData could legitimately revise.
        self.assertTrue(100 < row["Close"] < 400, f"AAPL close out of range: {row['Close']}")

    def test_stock_has_volume(self):
        self.assertGreater(self.stock[0]["Volume"], 0)

    def test_index_volume_is_zero(self):
        # Indices come from the index endpoint and carry no volume — relied on by the DB schema.
        self.assertEqual(self.index[0]["Volume"], 0)
        self.assertTrue(3000 < self.index[0]["Close"] < 7000, f"SPX close out of range: {self.index[0]['Close']}")


@requires_creds
class NoDataBehaviour(unittest.TestCase):
    """service.py's on-demand backfill catches NoDataFoundError — pin that the library raises it."""

    def test_weekend_raises(self):
        with self.assertRaises(NoDataFoundError):
            data_source.load_thetadata("AAPL", NON_TRADING_DAY, NON_TRADING_DAY)


if __name__ == "__main__":
    unittest.main()
