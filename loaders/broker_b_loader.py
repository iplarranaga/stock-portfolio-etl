"""
Parses Broker B portfolio export XLS files and loads them into DuckDB raw schema.

Broker B XLS structure:
  Rows 1–6:  metadata (account number, holder name, export date) — skipped
  Row 7:     column headers (header=6 in 0-indexed pandas)
  Row 8+:    data

File routing by filename prefix:
  Dividendos_*.xls*  → raw.broker_b_dividends  (30 rows, OPERACIÓN = DIVIDENDO)
  Operaciones_*.xls* → raw.broker_b_trades     (43 rows, OPERACIÓN = COMPRA/VENTA)

Columns after rename:
  FECHA                   → fecha
  OPERACIÓN               → operacion
  VALOR                   → valor           (company name, not ticker symbol)
  MERCADO                 → mercado
  TÍTULOS                 → titulos         (number of shares)
  PRECIO EN DIVISA ORIGEN → precio_en_divisa_origen
  IMPORTE TOTAL (€)       → importe_total_eur
"""

import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from loaders.utils import DATA_ROOT, get_connection

DATA_DIR = DATA_ROOT / "broker_b"

COLUMN_RENAME = {
    "FECHA": "fecha",
    "OPERACIÓN": "operacion",
    "VALOR": "valor",
    "MERCADO": "mercado",
    "TÍTULOS": "titulos",
    "PRECIO EN DIVISA ORIGEN": "precio_en_divisa_origen",
    "IMPORTE TOTAL (€)": "importe_total_eur",
}

EXCEL_SUFFIXES = {".xls", ".xlsx"}

ROUTES = [
    ("Dividendos_*", "broker_b_dividends"),
    ("Operaciones_*", "broker_b_trades"),
]


def _load_xls(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, header=6, dtype=str)
    # Drop merged-cell artifact columns (Unnamed: *)
    df = df[[c for c in df.columns if not c.startswith("Unnamed")]]
    df = df.rename(columns=COLUMN_RENAME)
    df = df.dropna(how="all")
    df["source_file"] = path.name
    return df


def _write(conn, df: pd.DataFrame, table: str) -> None:
    conn.execute(f"DROP TABLE IF EXISTS raw.{table}")
    conn.register("_tmp", df)
    conn.execute(f"CREATE TABLE raw.{table} AS SELECT * FROM _tmp")
    conn.unregister("_tmp")
    print(f"  [ok]   raw.{table}: {len(df)} rows")


def load_all() -> None:
    conn = get_connection()
    try:
        for pattern, table in ROUTES:
            files = sorted(
                f for f in DATA_DIR.glob(pattern) if f.suffix.lower() in EXCEL_SUFFIXES
            )
            if not files:
                print(f"  [warn] no files matching {pattern}")
                continue
            frames = []
            for f in files:
                df = _load_xls(f)
                print(f"  {f.name}: {len(df)} rows")
                frames.append(df)
            combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
            if not combined.empty:
                _write(conn, combined, table)
    finally:
        conn.close()


if __name__ == "__main__":
    load_all()
