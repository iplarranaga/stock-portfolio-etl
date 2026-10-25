-- Union trade history across brokers.
-- Broker A: has commission detail and exact price; Broker B: only net total.
-- Columns absent in Broker B are null-padded for schema alignment.
select
    ticker,
    trade_date,
    side,
    quantity,
    price,
    gross_amount,
    commission,
    net_cash,
    currency,
    fx_rate_to_base,
    net_cash_base,
    broker,
    source_file
from {{ ref('stg_broker_a_trades') }}

union all

select
    ticker,
    trade_date,
    side,
    quantity,
    price,
    null::decimal(18, 4)    as gross_amount,   -- Broker B doesn't separate gross from net
    null::decimal(18, 4)    as commission,
    net_cash,
    currency,
    fx_rate_to_base,
    net_cash_base,
    broker,
    source_file
from {{ ref('stg_broker_b_trades') }}

union all

select
    ticker,
    trade_date,
    side,
    quantity,
    price,
    gross_amount,
    commission,
    net_cash,
    currency,
    fx_rate_to_base,
    net_cash_base,
    broker,
    source_file
from {{ ref('stg_manual_trades') }}
