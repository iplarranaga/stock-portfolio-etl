-- Realised P&L from closed trades per ticker/broker.
-- net_cash_base: positive for sells (proceeds), negative for buys (cost).
-- Summing net_cash_base across all trades = realised P&L (open positions excluded).
with trade_summary as (
    select
        ticker,
        broker,
        sum(case when side = 'BUY'  then abs(quantity) else 0 end) as total_bought,
        sum(case when side = 'SELL' then abs(quantity) else 0 end) as total_sold,
        -- buys are negative net_cash (money out), sells are positive (money in)
        sum(net_cash_base)                                          as realised_pnl_base,
        sum(case when side = 'BUY'  then net_cash_base else 0 end) as cost_basis_base,
        sum(case when side = 'SELL' then net_cash_base else 0 end) as proceeds_base,
        min(trade_date)                                             as first_trade_date,
        max(trade_date)                                             as last_trade_date
    from {{ ref('int_trades') }}
    group by 1, 2
)

select
    ticker,
    broker,
    total_bought,
    total_sold,
    cost_basis_base,
    proceeds_base,
    realised_pnl_base,
    first_trade_date,
    last_trade_date
from trade_summary
where ticker not like '%.D%'   -- exclude scrip-dividend rights (dividendo flexible)
order by realised_pnl_base desc
