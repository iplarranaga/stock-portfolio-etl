"""
Loads the ECB's official euro reference exchange rates (published ~16:00 CET
on TARGET business days) into raw.ecb_fx_rates. These are the rates used to
convert foreign-currency amounts to euros for the Spanish tax report.

Source: ECB Data Portal, series EXR.D.<CCY>.EUR.SP00.A
Rates are quoted as units of the currency per 1 EUR (e.g. USD 1.08).

Each run reloads the full history from START_DATE (a few KB per currency).
"""

import io
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from loaders.utils import get_connection

CURRENCIES = ["USD", "GBP"]
START_DATE = "2023-01-01"
URL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/"
    "D.{currencies}.EUR.SP00.A?startPeriod={start}&format=csvdata"
)


def fetch() -> pd.DataFrame:
    url = URL.format(currencies="+".join(CURRENCIES), start=START_DATE)
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    df = pd.read_csv(io.BytesIO(response.content))
    return pd.DataFrame({
        "rate_date": pd.to_datetime(df["TIME_PERIOD"]).dt.date,
        "currency": df["CURRENCY"],
        "units_per_eur": df["OBS_VALUE"].astype(float),
    }).dropna()


def load() -> None:
    df = fetch()
    conn = get_connection()
    try:
        conn.execute("DROP TABLE IF EXISTS raw.ecb_fx_rates")
        conn.register("_tmp", df)
        conn.execute("CREATE TABLE raw.ecb_fx_rates AS SELECT * FROM _tmp")
        conn.unregister("_tmp")
    finally:
        conn.close()
    for ccy, g in df.groupby("currency"):
        print(f"  [ok]   {ccy}: {len(g)} rates, {g.rate_date.min()} → {g.rate_date.max()}")


if __name__ == "__main__":
    load()
