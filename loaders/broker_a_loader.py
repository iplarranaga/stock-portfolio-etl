"""
Parses Broker A XML statement files and loads them into DuckDB raw schema.

File routing by filename prefix:
  Operaciones_*.xml  → <Trade> elements      → raw.broker_a_trades
  dividendos_*.xml   → <ChangeInDividendAccrual> elements → raw.broker_a_dividend_accruals

All years are concatenated before writing so re-running replaces all data.

Trade attributes:   symbol, tradeDate, quantity, tradePrice, ibCommission,
                    currency, fxRateToBase, tradeMoney
  - quantity < 0 and tradeMoney < 0 = sell; > 0 = buy
  - net_cash computed in staging as tradeMoney + ibCommission

Dividend attributes: symbol, payDate, grossAmount, tax, netAmount,
                     currency, fxRateToBase
  - tax is positive (a cost); netAmount = grossAmount - tax
  - pairs of original + reversal entries can exist (both kept)
"""

import sys
from pathlib import Path
import xml.etree.ElementTree as ET
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from loaders.utils import DATA_ROOT, get_connection

DATA_DIR = DATA_ROOT / "broker_a"


def _parse_all(pattern: str, element_tag: str) -> pd.DataFrame:
    files = sorted(DATA_DIR.glob(pattern))
    if not files:
        print(f"  [warn] no files matching {pattern}")
        return pd.DataFrame()
    frames = []
    for f in files:
        root = ET.parse(f).getroot()
        rows = [e.attrib for e in root.iter(element_tag)]
        if rows:
            df = pd.DataFrame(rows)
            df["source_file"] = f.name
            frames.append(df)
            print(f"  {f.name}: {len(rows)} {element_tag} rows")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _write(conn, df: pd.DataFrame, table: str) -> None:
    if df.empty:
        print(f"  [skip] {table} — no data")
        return
    conn.execute(f"DROP TABLE IF EXISTS raw.{table}")
    conn.register("_tmp", df)
    conn.execute(f"CREATE TABLE raw.{table} AS SELECT * FROM _tmp")
    conn.unregister("_tmp")
    print(f"  [ok]   raw.{table}: {len(df)} rows total")


def load_all() -> None:
    conn = get_connection()
    try:
        print("Loading Broker A trades...")
        trades = _parse_all("Operaciones_*.xml", "Trade")
        _write(conn, trades, "broker_a_trades")

        print("Loading Broker A dividend accruals...")
        divs = _parse_all("dividendos_*.xml", "ChangeInDividendAccrual")
        _write(conn, divs, "broker_a_dividend_accruals")
    finally:
        conn.close()


if __name__ == "__main__":
    load_all()
