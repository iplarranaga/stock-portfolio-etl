import os

import duckdb
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB_PATH = Path(os.environ.get("CARTERA_DB_PATH", ROOT / "database" / "cartera.db"))

# Input folder; set CARTERA_DATA_DIR=sample_data to run on the fake demo data
DATA_ROOT = ROOT / os.environ.get("CARTERA_DATA_DIR", "data")


def get_connection(db_path: Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    conn.execute("CREATE SCHEMA IF NOT EXISTS raw")
    return conn
