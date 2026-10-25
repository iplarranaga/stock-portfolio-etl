-- Ticker metadata, keyed by broker symbol (Broker A) or company name (Broker B).
-- Loaded from data/manual/ticker_metadata.csv so holdings stay out of git.
select
    ticker,
    company_name,
    sector,
    country_code,
    canonical_ticker,
    isin
from {{ source('manual', 'ticker_metadata') }}
