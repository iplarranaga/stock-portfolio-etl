# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

ETL pipeline for a dividend investment portfolio (`Cartera Dividendos`).

- **Ingestion**: Python loaders parse raw files → DuckDB `raw` schema
- **Transformation**: dbt (`dbt_cartera/`) transforms raw tables → staging → intermediate → marts
- **Database**: DuckDB at `database/cartera.db` (gitignored)
- **Sources**: Broker A XML statement exports (`data/broker_a/`), Broker B XLS exports (`data/broker_b/`) and hand-kept CSVs (`data/manual/`)
- **Private data stays out of git**: everything under `data/` and `database/` plus `.env` is gitignored, including `data/manual/ticker_metadata.csv`

## Commands

### Full refresh
```bash
./refresh.sh   # loaders → dbt seed/run/test → export_to_sheets.py; stops on first error
```

### Sample data (fictional, committed)
```bash
CARTERA_DATA_DIR=sample_data ./refresh.sh   # writes database/sample_data.db, skips the sheet export
python sample_data/generate.py              # regenerate sample_data/ after editing the portfolio in it
```
CI (`.github/workflows/pipeline.yml`) runs this on every push. Keep it passing when changing models.

### Dashboard
```bash
streamlit run app.py   # from the repo root; opens at http://localhost:8501
CARTERA_DB_PATH=database/sample_data.db streamlit run app.py   # on the sample data
```

### Google Sheet export (main dashboard)
```bash
python export_to_sheets.py   # after dbt run; overwrites only the data_* tabs of control_cartera_dividendos
```
Sheet: `CARTERA_SHEET_ID` from the gitignored `.env` (`refresh.sh` loads it). Auth: service account JSON at `~/.config/gspread/service_account.json` (or `GOOGLE_SERVICE_ACCOUNT_FILE`); the sheet must be shared with the service account e-mail as Editor.

### Ingestion (Python)
```bash
# Install dependencies (requires Python ≤ 3.12 for dbt compatibility)
pip install -r requirements.txt

# Load Broker A XML files (picks the latest file in data/broker_a/)
python loaders/broker_a_loader.py

# Load Broker B XLS files (loads all files in data/broker_b/)
python loaders/broker_b_loader.py

# Load hand-kept CSVs (Broker C trades/dividends, ticker metadata) from data/manual/
python loaders/manual_loader.py

# Load ECB euro reference rates (full history since 2023, from the ECB Data API)
python loaders/ecb_loader.py
```

### dbt (run from dbt_cartera/)
```bash
cd dbt_cartera

dbt debug                          # verify connection
dbt seed                           # load country_withholding_rates.csv
dbt run                            # build all models
dbt test                           # run schema tests
dbt run --select staging           # run only staging layer
dbt run --select marts.dividends   # run only dividend mart
```

### Query results
```bash
duckdb database/cartera.db "SELECT * FROM main.fct_dividends LIMIT 10"
duckdb database/cartera.db "SELECT * FROM main.fct_positions"
duckdb database/cartera.db "SELECT * FROM main.fct_tax_report"
```

## Architecture

```
raw.*          (DuckDB, written by Python loaders)
  broker_a_trades            ← Operaciones_*.xml (all years, <Trade> elements)
  broker_a_dividend_accruals ← dividendos_*.xml  (all years, <ChangeInDividendAccrual>)
  broker_b_dividends         ← Dividendos_*.xls
  broker_b_trades            ← Operaciones_*.xls
  ecb_fx_rates               ← ECB Data API (units of currency per 1 EUR)
  manual_trades, manual_dividends ← data/manual/*_manual.csv (Broker C)
  ticker_metadata            ← data/manual/ticker_metadata.csv

staging.*
  stg_broker_a_dividend_accruals, stg_broker_a_trades
  stg_broker_b_dividends, stg_broker_b_trades
  stg_manual_trades, stg_manual_dividends
  stg_ticker_metadata

intermediate.*
  int_dividends    ← union of Broker A + Broker B dividends
  int_trades       ← union of Broker A + Broker B trades
  int_ecb_fx_rates ← ECB rate per currency per calendar day (forward-filled)

marts.*
  dividends/  fct_dividends
  portfolio/  fct_positions, fct_pnl
  tax/        fct_tax_report, fct_capital_gains

seeds.*        country_withholding_rates
```

**Key rules:**
- Loaders write only to `raw.*`; dbt reads raw via `sources.yml` — never writes to it
- Broker A dividends: `grossAmount`, `tax` (positive, a cost), `netAmount` are all in each record — no join needed
- Broker A dividend accruals come in pairs (+ on ex-date, − on pay date); never sum them. `stg_broker_a_dividend_accruals` keeps one row per dividend with the pay-date FX rate and an `is_paid` flag
- Broker exports overlap in date range (all files are loaded); staging models collapse overlaps by numbering identical rows per file
- Broker B dividends: export has net only (after origin tax + Spain's 19%); staging derives `gross_amount` = titulos × precio and `withholding_tax` = gross − net (total withheld). `fct_tax_report` splits foreign vs Spanish withholding (Broker B foreign part estimated at the seed treaty rate)
- Ticker metadata is a raw table, not a seed, so holdings never land in git. Staging resolves broker symbols via `stg_ticker_metadata`; marts join `int_ticker_metadata` (one row per canonical ticker)
- Broker A trade `side`: inferred from `quantity` sign (positive = BUY, negative = SELL)
- `net_cash` sign convention for all brokers: negative = money out (buy, fees included), positive = money in (sell, net of fees). Broker A: `-tradeMoney + ibCommission`
- Tax amounts (`*_eur` in fct_dividends, fct_tax_report, fct_capital_gains) use the ECB rate on the pay/trade date; `*_base` keep the broker's rate. Amounts the broker settled in euros (Broker B, Broker C, Broker A EUR) use the euros actually paid
- `fct_capital_gains`: FIFO per ticker across all brokers over the full trade history; only sales from dbt var `capital_gains_from` (2026-01-01) are output. Free rights (`.D` tickers) cost 0; two-month rule defers losses when the same ticker was bought within ±2 months
- Broker B XLS header is at spreadsheet row 7 (pandas `header=6`); rows 1–6 are account metadata

## dbt Python compatibility

dbt works on Python 3.14 as of `mashumaro>=3.22`. If dbt fails to import, run `pip3 install --upgrade mashumaro`.
