#!/usr/bin/env bash
# Full portfolio refresh: load raw data, build dbt models, export to Google Sheet.
# Usage: ./refresh.sh                            (real exports in data/)
#        CARTERA_DATA_DIR=sample_data ./refresh.sh  (fake demo data)
set -euo pipefail

cd "$(dirname "$0")"

# Local settings (CARTERA_SHEET_ID, ...) live in the gitignored .env
if [ -f .env ]; then
  set -a; . ./.env; set +a
fi

# Any other data folder (e.g. sample_data) gets its own database and never
# touches the real Google Sheet
if [ "${CARTERA_DATA_DIR:-data}" != "data" ]; then
  export CARTERA_DB_PATH="$PWD/database/$(basename "$CARTERA_DATA_DIR").db"
  unset CARTERA_SHEET_ID
fi

echo "==> Loading Broker A"
python3 loaders/broker_a_loader.py

echo "==> Loading Broker B"
python3 loaders/broker_b_loader.py

echo "==> Loading manual CSVs and ticker metadata"
python3 loaders/manual_loader.py

echo "==> Loading ECB FX rates"
python3 loaders/ecb_loader.py

echo "==> Running dbt"
(
  cd dbt_cartera
  dbt seed
  dbt run
  dbt test
)

if [ -n "${CARTERA_SHEET_ID:-}" ]; then
  echo "==> Exporting to Google Sheet"
  python3 export_to_sheets.py
else
  echo "==> CARTERA_SHEET_ID not set, skipping Google Sheet export"
fi

echo "==> Refresh complete"
