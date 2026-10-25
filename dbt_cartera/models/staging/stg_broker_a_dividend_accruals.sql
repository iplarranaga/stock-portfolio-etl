-- Broker A <ChangeInDividendAccrual> records come in pairs per dividend:
--   +gross on the ex-date (accrual posted)
--   -gross on the pay date (accrual released when the cash is paid)
-- Summing both nets every dividend to zero, so this model returns one row per
-- dividend: amounts from the positive accrual, FX rate from the pay-date
-- reversal (the rate that applies for tax), falling back to the ex-date rate
-- while the dividend is still unpaid.
with source as (
    select * from {{ source('broker_a', 'broker_a_dividend_accruals') }}
),

renamed as (
    select
        coalesce(tm.canonical_ticker, source.symbol)    as ticker,
        strptime(payDate, '%Y%m%d')::date               as pay_date,
        cast(grossAmount as decimal(18, 4))             as gross_amount,
        cast(tax as decimal(18, 4))                     as withholding_tax,   -- positive value (cost)
        cast(netAmount as decimal(18, 4))               as net_amount,         -- grossAmount - tax
        currency,
        cast(fxRateToBase as decimal(18, 6))            as fx_rate_to_base,
        source_file
    from source
    left join {{ ref('stg_ticker_metadata') }} tm on tm.ticker = source.symbol
),

-- Broker A XML statement exports have overlapping date windows (e.g. a monthly
-- export and a year-to-date export both report the same accrual event).
-- Number identical rows within each file, then keep one row per
-- (event, occurrence) so overlaps collapse but genuine repeats survive.
numbered as (
    select
        *,
        row_number() over (
            partition by
                source_file, ticker, pay_date, gross_amount, withholding_tax,
                net_amount, currency, fx_rate_to_base
        ) as occurrence
    from renamed
),

deduped as (
    select * exclude (rn, occurrence)
    from (
        select
            *,
            row_number() over (
                partition by
                    ticker, pay_date, gross_amount, withholding_tax,
                    net_amount, currency, fx_rate_to_base, occurrence
                order by source_file desc
            ) as rn
        from numbered
    )
    where rn = 1
),

-- When Broker A re-accrues a dividend (e.g. corrected withholding), the same gross
-- shows up twice with different tax. Keep one: the highest withholding, which
-- matches the statutory rate in the cases seen (e.g. Germany: 26.375%).
accruals as (
    select *
    from deduped
    where gross_amount > 0
    qualify row_number() over (
        partition by ticker, pay_date, currency, gross_amount
        order by withholding_tax desc
    ) = 1
),

payments as (
    select
        ticker,
        pay_date,
        currency,
        max(fx_rate_to_base) as pay_fx_rate_to_base
    from deduped
    where gross_amount < 0
    group by all
),

final as (
    select
        a.ticker,
        a.pay_date,
        a.gross_amount,
        a.withholding_tax,
        a.net_amount,
        a.currency,
        coalesce(p.pay_fx_rate_to_base, a.fx_rate_to_base)                     as fx_rate_to_base,
        a.gross_amount    * coalesce(p.pay_fx_rate_to_base, a.fx_rate_to_base) as gross_amount_base,
        a.withholding_tax * coalesce(p.pay_fx_rate_to_base, a.fx_rate_to_base) as withholding_tax_base,
        a.net_amount      * coalesce(p.pay_fx_rate_to_base, a.fx_rate_to_base) as net_amount_base,
        p.ticker is not null                                                    as is_paid,
        a.source_file,
        'Broker A'                                                              as broker
    from accruals a
    left join payments p
        on  p.ticker   = a.ticker
        and p.pay_date = a.pay_date
        and p.currency = a.currency
)

select * from final
