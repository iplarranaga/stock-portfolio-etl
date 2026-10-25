-- Available attributes: symbol, tradeDate, quantity, tradePrice,
-- ibCommission, currency, fxRateToBase, tradeMoney
-- Side is inferred from quantity sign: positive = BUY, negative = SELL
-- tradeMoney is positive for buys and ibCommission negative, so cash flow is
-- -tradeMoney + ibCommission: negative = money out (buy, fees added to cost),
-- positive = money in (sell, fees deducted from proceeds), as in Broker B.
with source as (
    select * from {{ source('broker_a', 'broker_a_trades') }}
),

renamed as (
    select
        coalesce(tm.canonical_ticker, source.symbol)        as ticker,
        strptime(tradeDate, '%Y%m%d')::date                 as trade_date,
        cast(quantity as decimal(18, 6))                    as quantity,
        cast(tradePrice as decimal(18, 6))                  as price,
        cast(tradeMoney as decimal(18, 4))                  as gross_amount,
        cast(ibCommission as decimal(18, 4))                as commission,
        -cast(tradeMoney as decimal(18, 4))
            + cast(ibCommission as decimal(18, 4))          as net_cash,
        currency,
        cast(fxRateToBase as decimal(18, 6))                as fx_rate_to_base,
        (-cast(tradeMoney as decimal(18, 4))
            + cast(ibCommission as decimal(18, 4)))
            * cast(fxRateToBase as decimal(18, 6))          as net_cash_base,
        case when cast(quantity as decimal) > 0
            then 'BUY' else 'SELL'
        end                                                 as side,
        source_file,
        'Broker A'                                          as broker
    from source
    left join {{ ref('stg_ticker_metadata') }} tm on tm.ticker = source.symbol
)

-- Exclude FX conversion pairs (e.g. EUR.USD, EUR.GBP) — not investment positions
select * from renamed
where ticker not like '%.%'
