with src as (
    select * from {{ source('manual', 'manual_dividends') }}
)

select
    ticker,
    cast(pay_date as date)                              as pay_date,
    coalesce(currency, 'EUR')                           as currency,
    1.0::decimal(18, 6)                                 as fx_rate_to_base,
    cast(gross_amount_eur as decimal(18, 4))            as gross_amount,
    cast(gross_amount_eur as decimal(18, 4))            as gross_amount_base,
    cast(withholding_tax_eur as decimal(18, 4))         as withholding_tax,
    cast(withholding_tax_eur as decimal(18, 4))         as withholding_tax_base,
    cast(net_amount_eur as decimal(18, 4))              as net_amount,
    cast(net_amount_eur as decimal(18, 4))              as net_amount_base,
    broker,
    source_file
from src
where net_amount_eur is not null
