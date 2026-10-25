with src as (
    select * from {{ source('manual', 'manual_trades') }}
)

select
    ticker,
    cast(trade_date as date)                                                         as trade_date,
    upper(side)                                                                      as side,
    case upper(side)
        when 'BUY'  then  cast(quantity as integer)
        when 'SELL' then -cast(quantity as integer)
        else              cast(quantity as integer)
    end                                                                              as quantity,
    -- unit price approximated from total cost (no commission detail)
    round(
        cast(net_cash_eur as decimal(18, 4)) / cast(quantity as integer),
        4
    )                                                                                as price,
    null::decimal(18, 4)                                                             as gross_amount,
    null::decimal(18, 4)                                                             as commission,
    case upper(side)
        when 'BUY'  then -cast(net_cash_eur as decimal(18, 4))
        when 'SELL' then  cast(net_cash_eur as decimal(18, 4))
        else              cast(net_cash_eur as decimal(18, 4))
    end                                                                              as net_cash,
    coalesce(currency, 'EUR')                                                        as currency,
    1.0::decimal(18, 6)                                                              as fx_rate_to_base,
    case upper(side)
        when 'BUY'  then -cast(net_cash_eur as decimal(18, 4))
        when 'SELL' then  cast(net_cash_eur as decimal(18, 4))
        else              cast(net_cash_eur as decimal(18, 4))
    end                                                                              as net_cash_base,
    broker,
    source_file
from src
