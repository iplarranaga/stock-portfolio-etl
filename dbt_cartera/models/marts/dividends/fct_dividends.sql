-- *_base columns use the broker's own FX rate; *_eur columns use the ECB
-- reference rate on the pay date (the rate for the Spanish tax return).
-- Broker B and Broker C pay in euros already, so their *_eur equal *_base.
with dividends as (
    select * from {{ ref('int_dividends') }}
),

fx as (
    select * from {{ ref('int_ecb_fx_rates') }}
)

select
    d.ticker,
    coalesce(m.company_name, d.ticker)  as company_name,
    coalesce(m.sector, 'Unknown')       as sector,
    m.country_code,
    d.pay_date,
    date_trunc('year', d.pay_date)      as dividend_year,
    date_trunc('month', d.pay_date)     as dividend_month,
    d.currency,
    d.fx_rate_to_base,
    d.gross_amount,
    d.gross_amount_base,
    d.withholding_tax,
    d.withholding_tax_base,
    d.net_amount,
    d.net_amount_base,
    case
        when d.gross_amount is not null and d.gross_amount > 0
            then round(d.withholding_tax / d.gross_amount * 100, 2)
    end                                 as effective_withholding_rate_pct,
    d.broker,
    d.source_file,
    fx.units_per_eur                    as ecb_units_per_eur,
    round(d.gross_amount   / fx.units_per_eur, 2)  as gross_amount_eur,
    round(d.withholding_tax / fx.units_per_eur, 2) as withholding_tax_eur,
    round(d.gross_amount   / fx.units_per_eur, 2)
        - round(d.withholding_tax / fx.units_per_eur, 2)
                                        as net_amount_eur
from dividends d
left join {{ ref('int_ticker_metadata') }} m using (ticker)
left join fx on fx.rate_date = d.pay_date and fx.currency = d.currency
