"""
Writes the made-up demo portfolio in sample_data/ in the same formats as the
real broker exports, so the pipeline runs end to end without private data:

    CARTERA_DATA_DIR=sample_data ./refresh.sh

Every company, ticker, ISIN and amount here is fictional. The generated files
are committed; re-run this script only after changing the portfolio below.

The portfolio is small but exercises the tricky paths of the models:
  - ACME (USD): a 2026 sale at a loss with a repurchase 3 weeks later, so the
    two-month rule defers part of the loss
  - HDL (EUR, Germany): a 2026 sale at a gain, 26.375% dividend withholding
  - NRTH (GBP): dividends with no origin withholding
  - FRV: bought at Broker C and later at Broker B, sold at Broker B; FIFO takes the
    older Broker C shares first
  - SOLE.D: free subscription rights sold at Broker B (acquisition cost 0)
  - Broker A dividend accruals as +/- pairs, one still unpaid, and overlapping
    Broker A and Broker B exports that staging must collapse
  - an EUR.USD currency conversion that staging must drop
"""

import csv
import datetime as dt
import xml.etree.ElementTree as ET
from pathlib import Path

from openpyxl import Workbook

OUT = Path(__file__).parent
TODAY = dt.date(2026, 10, 25)  # fixed so the files don't change between runs

# Broker FX rate (EUR per unit of currency), roughly by year
FX = {"USD": {2024: 0.92, 2025: 0.89, 2026: 0.86}, "GBP": {2024: 1.17, 2025: 1.18, 2026: 1.15},
      "EUR": {2024: 1.0, 2025: 1.0, 2026: 1.0}}

METADATA = [
    # ticker (broker symbol or Broker B name), company_name, sector, country_code, canonical_ticker, isin
    ("ACME", "Acme Robotics Inc.", "Industrials", "US", "ACME", "US0ACME00001"),
    ("NRTH", "Northwind Utilities plc", "Utilities", "GB", "NRTH", "GB0NRTH00002"),
    ("HDL", "Heidler Chemie AG", "Materials", "DE", "HDL", "DE000HDL0003"),
    ("SOLE", "Ibersol Energía S.A.", "Utilities", "ES", "SOLE", "ES0SOLE00004"),
    ("IBERSOL ENERGIA", "Ibersol Energía S.A.", "Utilities", "ES", "SOLE", "ES0SOLE00004"),
    ("SOLE DERECHOS", "Ibersol Energía S.A. (derechos)", "Utilities", "ES", "SOLE.D", "ES0SOLE0D005"),
    ("BANCO CANTABRO", "Banco Cantábrico S.A.", "Financials", "ES", "BCAN", "ES0BCAN00006"),
    ("FRV", "Fromagerie Vallée S.A.", "Consumer Staples", "FR", "FRV", "FR000FRV0007"),
    ("FROMAGERIE VALLEE", "Fromagerie Vallée S.A.", "Consumer Staples", "FR", "FRV", "FR000FRV0007"),
]

# Broker A trades: date, symbol, quantity (+buy / -sell), price, commission, currency
BROKER_A_TRADES = [
    ("2024-02-12", "EUR.USD", 3500, 1.078, -2.00, "USD"),
    ("2024-02-12", "ACME", 40, 95.00, -1.00, "USD"),
    ("2024-05-20", "NRTH", 200, 9.80, -3.00, "GBP"),
    ("2024-09-09", "HDL", 25, 64.00, -1.25, "EUR"),
    ("2025-01-15", "NRTH", 100, 10.50, -3.00, "GBP"),
    ("2025-06-03", "ACME", 20, 120.00, -1.00, "USD"),
    ("2026-03-10", "ACME", -30, 88.00, -1.00, "USD"),
    ("2026-04-02", "ACME", 15, 90.00, -1.00, "USD"),
    ("2026-07-14", "HDL", -25, 78.00, -1.25, "EUR"),
]

# Broker A dividends: ex-date, pay date, symbol, dividend per share, currency, origin withholding rate
BROKER_A_DIVIDENDS = [
    *[(ex, pay, "ACME", 0.55, "USD", 0.15) for ex, pay in [
        ("2024-05-02", "2024-05-16"), ("2024-08-01", "2024-08-15"), ("2024-11-01", "2024-11-15"),
        ("2025-02-03", "2025-02-14"), ("2025-05-01", "2025-05-15"), ("2025-08-01", "2025-08-15"),
        ("2025-11-03", "2025-11-14"), ("2026-02-02", "2026-02-13"), ("2026-05-01", "2026-05-15"),
        ("2026-08-03", "2026-08-14"), ("2026-10-23", "2026-11-13"),  # accrued, not paid yet
    ]],
    *[(ex, pay, "NRTH", 0.30, "GBP", 0.0) for ex, pay in [
        ("2024-11-21", "2024-12-20"), ("2025-06-05", "2025-07-04"),
        ("2025-11-20", "2025-12-19"), ("2026-06-04", "2026-07-03"),
    ]],
    ("2025-04-28", "2025-04-30", "HDL", 2.10, "EUR", 0.26375),
    ("2026-04-27", "2026-04-29", "HDL", 2.25, "EUR", 0.26375),
]

# Broker B trades: date, name, COMPRA/VENTA, shares, price, total EUR (fees included)
BROKER_B_TRADES = [
    ("2024-03-05", "IBERSOL ENERGIA", "COMPRA", 150, 12.40, 1868.00),
    ("2024-11-04", "BANCO CANTABRO", "COMPRA", 300, 5.20, 1566.00),
    ("2025-02-10", "IBERSOL ENERGIA", "COMPRA", 50, 13.10, 659.50),
    ("2025-09-15", "FROMAGERIE VALLEE", "COMPRA", 10, 210.00, 2108.00),
    ("2026-02-16", "FROMAGERIE VALLEE", "VENTA", 10, 225.00, 2242.00),
    ("2026-06-22", "SOLE DERECHOS", "VENTA", 200, 0.21, 40.00),
]

# Broker B dividends: pay date, name, dividend per share (EUR), total withheld (origin + Spain's 19%)
BROKER_B_DIVIDENDS = [
    ("2024-07-15", "IBERSOL ENERGIA", 0.32, 0.19),
    ("2025-01-20", "IBERSOL ENERGIA", 0.30, 0.19),
    ("2025-05-02", "BANCO CANTABRO", 0.15, 0.19),
    ("2025-07-15", "IBERSOL ENERGIA", 0.34, 0.19),
    ("2025-11-03", "BANCO CANTABRO", 0.12, 0.19),
    ("2026-01-19", "IBERSOL ENERGIA", 0.33, 0.19),
    ("2026-05-04", "BANCO CANTABRO", 0.18, 0.19),
    ("2026-07-15", "IBERSOL ENERGIA", 0.36, 0.19),
]

# Broker C (no export, kept by hand)
MANUAL_TRADES = [("2024-04-08", "FRV", "BUY", 15, 2856.00, "EUR", "Broker C")]
MANUAL_DIVIDENDS = [("2024-05-21", "FRV", 15, 4.20), ("2025-05-20", "FRV", 15, 4.50),
                    ("2026-05-19", "FRV", 15, 4.80)]
FR_WITHHOLDING = 0.128


def _date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _shares_held(symbol: str, on: dt.date) -> int:
    return sum(q for d, s, q, *_ in BROKER_A_TRADES if s == symbol and _date(d) < on)


def _broker_b_shares_held(name: str, on: dt.date) -> int:
    return sum(n if op == "COMPRA" else -n
               for d, nm, op, n, *_ in BROKER_B_TRADES if nm == name and _date(d) < on)


def _xml_statement(path: Path, tag: str, rows: list[dict]) -> None:
    root = ET.Element("Statement", name=path.stem)
    parent = ET.SubElement(root, "Trades" if tag == "Trade" else "ChangeInDividendAccruals")
    for r in rows:
        ET.SubElement(parent, tag, {k: str(v) for k, v in r.items()})
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def write_broker_a() -> None:
    d = OUT / "broker_a"
    d.mkdir(exist_ok=True)
    trades = [{
        "symbol": s, "tradeDate": _date(day).strftime("%Y%m%d"), "quantity": q,
        "tradePrice": f"{p:.4f}", "ibCommission": f"{c:.2f}", "currency": ccy,
        "fxRateToBase": FX[ccy][_date(day).year], "tradeMoney": f"{q * p:.2f}",
    } for day, s, q, p, c, ccy in BROKER_A_TRADES]
    _xml_statement(d / "Operaciones_2024.xml", "Trade", [t for t in trades if t["tradeDate"] < "2025"])
    _xml_statement(d / "Operaciones_2025_2026.xml", "Trade", [t for t in trades if t["tradeDate"] >= "2025"])

    # One +accrual on the ex-date and one -reversal on the pay date per dividend
    events = []
    for ex, pay, s, dps, ccy, rate in BROKER_A_DIVIDENDS:
        gross = round(_shares_held(s, _date(ex)) * dps, 2)
        tax = round(gross * rate, 2)
        for day, sign in [(ex, 1), (pay, -1)]:
            if _date(day) > TODAY:
                continue
            events.append((day, {
                "symbol": s, "payDate": _date(pay).strftime("%Y%m%d"),
                "grossAmount": f"{sign * gross:.2f}", "tax": f"{sign * tax:.2f}",
                "netAmount": f"{sign * (gross - tax):.2f}", "currency": ccy,
                "fxRateToBase": FX[ccy][_date(day).year],
            }))
    # Year files, the 2026 one overlapping the last quarter of 2025
    for name, start, end in [("dividendos_2024.xml", "2024-01-01", "2024-12-31"),
                             ("dividendos_2025.xml", "2025-01-01", "2025-12-31"),
                             ("dividendos_2026.xml", "2025-10-01", "2026-12-31")]:
        _xml_statement(d / name, "ChangeInDividendAccrual",
                  [r for day, r in events if start <= day <= end])


def _broker_b_xlsx(path: Path, rows: list[tuple]) -> None:
    wb = Workbook()
    ws = wb.active
    for line in ["Cuenta: ES00 0000 0000 0000 0000 0000", "Titular: DEMO USER",
                 f"Fecha de exportación: {TODAY:%d/%m/%Y}", "Divisa: EUR", "", ""]:
        ws.append([line])
    ws.append(["FECHA", "OPERACIÓN", "VALOR", "MERCADO", "TÍTULOS",
               "PRECIO EN DIVISA ORIGEN", "IMPORTE TOTAL (€)"])
    for r in rows:
        ws.append(list(r))
    wb.save(path)


def write_broker_b() -> None:
    d = OUT / "broker_b"
    d.mkdir(exist_ok=True)
    _broker_b_xlsx(d / "Operaciones_2024_2026.xlsx", [
        (_date(day).strftime("%d/%m/%Y"), op, name, "MC" if "VALLEE" not in name else "EPA",
         n, p, total)
        for day, name, op, n, p, total in BROKER_B_TRADES])

    divs = []
    for day, name, dps, rate in BROKER_B_DIVIDENDS:
        n = _broker_b_shares_held(name, _date(day))
        gross = round(n * dps, 2)
        divs.append((day, (_date(day).strftime("%d/%m/%Y"), "DIVIDENDO", name, "MC", n, dps,
                           round(gross * (1 - rate), 2))))
    # Two exports whose date ranges overlap in the second half of 2025
    _broker_b_xlsx(d / "Dividendos_2024_2025.xlsx", [r for day, r in divs if day < "2026"])
    _broker_b_xlsx(d / "Dividendos_2025_2026.xlsx", [r for day, r in divs if day >= "2025-07"])


def _csv(path: Path, header: list[str], rows: list[tuple]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def write_manual() -> None:
    d = OUT / "manual"
    d.mkdir(exist_ok=True)
    _csv(d / "trades_manual.csv",
         ["trade_date", "ticker", "side", "quantity", "net_cash_eur", "currency", "broker"],
         [(day, t, side, q, f"{cash:.2f}", ccy, b) for day, t, side, q, cash, ccy, b in MANUAL_TRADES])
    rows = []
    for day, t, n, dps in MANUAL_DIVIDENDS:
        gross = round(n * dps, 2)
        tax = round(gross * FR_WITHHOLDING, 2)
        rows.append((day, t, f"{gross:.2f}", f"{tax:.2f}", f"{gross - tax:.2f}", "EUR", "Broker C"))
    _csv(d / "dividends_manual.csv",
         ["pay_date", "ticker", "gross_amount_eur", "withholding_tax_eur", "net_amount_eur",
          "currency", "broker"], rows)
    _csv(d / "ticker_metadata.csv",
         ["ticker", "company_name", "sector", "country_code", "canonical_ticker", "isin"], METADATA)


if __name__ == "__main__":
    write_broker_a()
    write_broker_b()
    write_manual()
    print(f"Sample data written to {OUT}")
