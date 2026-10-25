"""
Loads hand-maintained CSV files: trades/dividends for brokers without export
capability (e.g. Broker C) and the ticker metadata (kept out of git, like all of data/).

Files (in data/manual/, or $CARTERA_DATA_DIR/manual/):
  trades_manual.csv    → raw.manual_trades
  dividends_manual.csv → raw.manual_dividends
  ticker_metadata.csv  → raw.ticker_metadata

CSV schemas:
  trades:    trade_date, ticker, side, quantity, net_cash_eur, currency, broker
  dividends: pay_date, ticker, gross_amount_eur, withholding_tax_eur, net_amount_eur, currency, broker
  metadata:  ticker, company_name, sector, country_code, canonical_ticker, isin
             (ticker = broker symbol or Broker B company name; canonical_ticker = ticker used in marts)
"""

import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from loaders.utils import DATA_ROOT, get_connection

DATA_DIR = DATA_ROOT / "manual"

ROUTES = [
    ("trades_manual.csv",    "manual_trades"),
    ("dividends_manual.csv", "manual_dividends"),
    ("ticker_metadata.csv",  "ticker_metadata"),
]


def _write(conn, df: pd.DataFrame, table: str) -> None:
    conn.execute(f"DROP TABLE IF EXISTS raw.{table}")
    conn.register("_tmp", df)
    conn.execute(f"CREATE TABLE raw.{table} AS SELECT * FROM _tmp")
    conn.unregister("_tmp")
    print(f"  [ok]   raw.{table}: {len(df)} rows")


def load_all() -> None:
    conn = get_connection()
    try:
        for filename, table in ROUTES:
            path = DATA_DIR / filename
            if not path.exists():
                print(f"  [warn] {filename} not found, skipping")
                continue
            df = pd.read_csv(path, dtype=str)
            df = df.dropna(how="all")
            if table != "ticker_metadata":
                df["source_file"] = filename
            print(f"  {filename}: {len(df)} rows")
            _write(conn, df, table)
    finally:
        conn.close()


if __name__ == "__main__":
    load_all()
