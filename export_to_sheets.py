"""
Publishes the dbt marts to the Google Sheet `control_cartera_dividendos`,
which is the portfolio dashboard. The ETL is the source of truth: each run
fully overwrites the data_* tabs below; every other tab (Dashboard, Cartera,
...) is never touched, so formulas there should read from data_* tabs.

    data_positions   ← main_marts.fct_positions      (one row per ticker × broker)
    data_dividends   ← main_marts.fct_dividends      (one row per dividend)
    data_trades      ← main_intermediate.int_trades  (one row per trade)
    data_tax         ← main_marts.fct_tax_report     (year × ticker × currency × broker)
    data_capital_gains ← main_marts.fct_capital_gains (sale × FIFO purchase lot)
    data_meta        ← refresh timestamp and row counts

Euro amounts in data_dividends (columns N–P), data_tax and data_capital_gains
use the ECB reference rate, as required for the Spanish tax return. Sheet
formulas address columns by letter, so keep column order stable.

Values are written as real numbers and ISO dates (USER_ENTERED), so the
sheet's locale formats them and formulas can use them directly.

Auth: a Google service account. Share the sheet with the service account's
e-mail (Editor) and put its JSON key at ~/.config/gspread/service_account.json
or point GOOGLE_SERVICE_ACCOUNT_FILE at it.

Usage (after `dbt run`):
    python export_to_sheets.py
    CARTERA_SHEET_ID=<id> python export_to_sheets.py   # another spreadsheet
"""

import datetime as dt
import decimal
import math
import os
import sys
from pathlib import Path

import duckdb
import gspread

sys.path.insert(0, str(Path(__file__).parent))
from loaders.utils import DB_PATH

SHEET_ID = os.environ["CARTERA_SHEET_ID"]
CREDENTIALS = os.environ.get(
    "GOOGLE_SERVICE_ACCOUNT_FILE",
    str(Path.home() / ".config" / "gspread" / "service_account.json"),
)

TABS = {
    "data_positions": """
        select ticker, broker, company_name, sector, country_code,
               quantity, avg_cost_price_base, cost_basis_base, last_trade_date
        from main_marts.fct_positions
        order by ticker, broker
    """,
    "data_dividends": """
        select pay_date, year(pay_date) as year, month(pay_date) as month,
               ticker, company_name, sector, country_code, broker, currency,
               fx_rate_to_base, gross_amount, withholding_tax, net_amount,
               gross_amount_eur, withholding_tax_eur, net_amount_eur,
               effective_withholding_rate_pct, ecb_units_per_eur
        from main_marts.fct_dividends
        order by pay_date, ticker
    """,
    "data_trades": """
        select trade_date, ticker, broker, side, quantity, price, currency,
               fx_rate_to_base, gross_amount, commission, net_cash, net_cash_base
        from main_intermediate.int_trades
        order by trade_date, ticker
    """,
    "data_tax": """
        select year(dividend_year) as year, country_code, country_name, ticker,
               currency, broker, gross_dividends_eur, withholding_tax_eur,
               foreign_withholding_eur, spanish_withholding_eur,
               net_dividends_eur, effective_withholding_rate_pct,
               expected_withholding_rate_pct, withholding_rate_variance_pct
        from main_marts.fct_tax_report
        order by year desc, ticker
    """,
    "data_capital_gains": """
        select sale_date, sale_year, ticker, company_name, isin, sale_broker,
               quantity, buy_date, buy_broker, acquisition_type, holding_days,
               currency, sale_ecb_units_per_eur, buy_ecb_units_per_eur,
               transmission_value_eur, acquisition_value_eur, gain_loss_eur,
               deferred_loss_eur, computable_gain_loss_eur,
               two_month_window_open, needs_review
        from main_marts.fct_capital_gains
        order by sale_date, ticker, buy_date
    """,
}


def _cell(value):
    """Convert a DuckDB value to something the Sheets API stores natively."""
    if value is None:
        return ""
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, float) and math.isnan(value):
        return ""
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()  # parsed as a date with USER_ENTERED
    return value


def _fetch(conn, sql: str) -> list[list]:
    cur = conn.execute(sql)
    header = [d[0] for d in cur.description]
    return [header] + [[_cell(v) for v in row] for row in cur.fetchall()]


def _write_tab(spreadsheet, title: str, rows: list[list]) -> None:
    n_rows, n_cols = max(len(rows), 2), len(rows[0])
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=n_rows, cols=n_cols)
    ws.clear()
    ws.resize(rows=n_rows, cols=n_cols)
    ws.update(values=rows, range_name="A1", value_input_option="USER_ENTERED")
    ws.freeze(rows=1)


def export() -> None:
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        data = {title: _fetch(conn, sql) for title, sql in TABS.items()}
    finally:
        conn.close()

    spreadsheet = gspread.service_account(filename=CREDENTIALS).open_by_key(SHEET_ID)

    for title, rows in data.items():
        _write_tab(spreadsheet, title, rows)
        print(f"{title}: {len(rows) - 1} rows")

    meta = [["key", "value"],
            ["refreshed_at", dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")]]
    meta += [[f"rows_{title}", len(rows) - 1] for title, rows in data.items()]
    _write_tab(spreadsheet, "data_meta", meta)
    print(f"Exported to https://docs.google.com/spreadsheets/d/{SHEET_ID}")


if __name__ == "__main__":
    export()
