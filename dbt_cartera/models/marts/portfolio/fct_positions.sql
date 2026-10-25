-- Current positions derived from trade history (no open-position snapshot available).
-- quantity > 0 means still held; rows with quantity ≈ 0 are fully closed.
with position as (
    select
        ticker,
        broker,
        sum(case when side = 'BUY'  then  quantity else 0 end)
            + sum(case when side = 'SELL' then quantity else 0 end)  as quantity,
        -- Average cost = total buy cost / total shares bought
        sum(case when side = 'BUY' then abs(net_cash_base) else 0 end)
            / nullif(sum(case when side = 'BUY' then abs(quantity) else 0 end), 0)
                                                                      as avg_cost_price_base,
        -- Cost of the shares still held (average cost method), so partial
        -- sells reduce it
        sum(case when side = 'BUY' then abs(net_cash_base) else 0 end)
            / nullif(sum(case when side = 'BUY' then abs(quantity) else 0 end), 0)
            * (sum(case when side = 'BUY'  then  quantity else 0 end)
               + sum(case when side = 'SELL' then quantity else 0 end))
                                                                      as cost_basis_base,
        max(trade_date)                                               as last_trade_date
    from {{ ref('int_trades') }}
    group by 1, 2
)

select
    p.ticker,
    p.broker,
    p.quantity,
    p.avg_cost_price_base,
    p.cost_basis_base,
    p.last_trade_date,
    coalesce(m.company_name, p.ticker)  as company_name,
    coalesce(m.sector, 'Unknown')       as sector,
    m.country_code
from position p
left join {{ ref('int_ticker_metadata') }} m using (ticker)
where round(p.quantity, 4) > 0
  and p.ticker not like '%.D%'   -- exclude scrip-dividend rights (dividendo flexible)
order by p.cost_basis_base desc
