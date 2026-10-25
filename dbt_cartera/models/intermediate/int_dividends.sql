-- Union Broker A and Broker B dividend records into a common schema.
-- Broker A withholding_tax is origin tax only; Broker B withholding_tax is origin + Spanish 19%.
-- Broker A accrual/reversal pairs are collapsed to one row per dividend in staging.
select
    ticker,
    pay_date,
    currency,
    fx_rate_to_base,
    gross_amount,
    gross_amount_base,
    withholding_tax,
    withholding_tax_base,
    net_amount,
    net_amount_base,
    broker,
    source_file
from {{ ref('stg_broker_a_dividend_accruals') }}

union all

select
    ticker,
    pay_date,
    currency,
    fx_rate_to_base,
    gross_amount,
    gross_amount_base,
    withholding_tax,
    withholding_tax_base,
    net_amount,
    net_amount_base,
    broker,
    source_file
from {{ ref('stg_broker_b_dividends') }}

union all

select
    ticker,
    pay_date,
    currency,
    fx_rate_to_base,
    gross_amount,
    gross_amount_base,
    withholding_tax,
    withholding_tax_base,
    net_amount,
    net_amount_base,
    broker,
    source_file
from {{ ref('stg_manual_dividends') }}
