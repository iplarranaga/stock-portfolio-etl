-- One metadata row per canonical ticker.
-- stg_ticker_metadata is keyed by broker symbol/name (an Broker A symbol or an Broker B
-- company name); marts work with canonical tickers, some of which have no row
-- of their own.
select
    canonical_ticker as ticker,
    company_name,
    sector,
    country_code,
    isin
from {{ ref('stg_ticker_metadata') }}
qualify row_number() over (
    partition by canonical_ticker
    order by (ticker = canonical_ticker) desc, ticker
) = 1
