-- Capital gains and losses from share sales for the Spanish tax return
-- (ganancias y pérdidas patrimoniales), one row per sale × purchase lot.
--
-- FIFO (art. 37.2 LIRPF): each sale uses up the oldest shares of the same
-- security first, across all brokers (homogeneous securities are pooled
-- regardless of where they are held).
--
-- Euro amounts:
--   - acquisition value = price × shares + buy fees, at the ECB rate on the buy date
--   - transmission value = price × shares − sell fees, at the ECB rate on the sale date
--   - trades the broker settled in euros (Broker B, Broker C, Broker A EUR) use the euros paid
-- Converting each side on its own date includes the currency gain or loss.
--
-- Subscription rights (tickers with ".D") received for free have cost 0.
-- Two-month rule (art. 33.5.f LIRPF): a loss is not computable this year in
-- the proportion that the same security was bought within 2 months before or
-- after the sale; it is deferred until those shares are sold.
with fx as (
    select * from {{ ref('int_ecb_fx_rates') }}
),

trades as (
    select
        row_number() over (order by t.trade_date, t.broker, t.ticker, t.side, t.source_file)
                                                        as trade_id,
        t.ticker,
        t.broker,
        t.trade_date,
        t.side,
        t.currency,
        abs(t.quantity)                                 as quantity,
        case when t.broker = 'Broker A' and t.currency <> 'EUR'
            then fx.units_per_eur end                   as ecb_units_per_eur,
        -- cash paid (buy) or received (sell), in euros
        abs(case when t.broker = 'Broker A' and t.currency <> 'EUR'
                 then t.net_cash / fx.units_per_eur
                 else t.net_cash_base end)::double      as amount_eur
    from {{ ref('int_trades') }} t
    left join fx on fx.rate_date = t.trade_date and fx.currency = t.currency
),

-- Each buy/sell covers a slice [qty_from, qty_to) of the security's
-- cumulative bought/sold quantity; overlapping slices are FIFO matches.
buys as (
    select
        *,
        sum(quantity) over (partition by ticker order by trade_date, trade_id) as qty_to,
        qty_to - quantity                                                     as qty_from
    from trades
    where side = 'BUY'
),

sells as (
    select
        *,
        sum(quantity) over (partition by ticker order by trade_date, trade_id) as qty_to,
        qty_to - quantity                                                     as qty_from
    from trades
    where side = 'SELL'
),

matched as (
    select
        s.trade_id                                      as sale_id,
        b.trade_id                                      as buy_id,
        least(s.qty_to, b.qty_to) - greatest(s.qty_from, b.qty_from)
                                                        as quantity,
        b.trade_date                                    as buy_date,
        b.broker                                        as buy_broker,
        b.ecb_units_per_eur                             as buy_ecb_units_per_eur,
        b.amount_eur / b.quantity                       as unit_cost_eur
    from sells s
    join buys b
        on  b.ticker = s.ticker
        and b.qty_from < s.qty_to
        and b.qty_to   > s.qty_from
),

-- Sold shares with no recorded purchase (free rights, or missing history)
unmatched as (
    select
        s.trade_id                                      as sale_id,
        null::bigint                                    as buy_id,
        s.quantity - coalesce(sum(m.quantity), 0)       as quantity,
        null::date                                      as buy_date,
        null::varchar                                   as buy_broker,
        null::double                                    as buy_ecb_units_per_eur,
        0.0                                             as unit_cost_eur
    from sells s
    left join matched m on m.sale_id = s.trade_id
    group by s.trade_id, s.quantity
    having s.quantity - coalesce(sum(m.quantity), 0) > 0.000001
),

lots as (
    select * from matched
    union all
    select * from unmatched
),

-- Shares of the same security bought within 2 months of each sale that this
-- sale did not use up
two_month_window as (
    select
        s.trade_id                                      as sale_id,
        sum(b.quantity - coalesce(m.quantity, 0))       as repurchased_quantity
    from sells s
    join buys b
        on  b.ticker = s.ticker
        and b.trade_date between s.trade_date - interval 2 month
                             and s.trade_date + interval 2 month
    left join matched m on m.sale_id = s.trade_id and m.buy_id = b.trade_id
    group by s.trade_id
),

gains as (
    select
        s.trade_date                                    as sale_date,
        year(s.trade_date)                              as sale_year,
        s.ticker,
        s.broker                                        as sale_broker,
        s.currency,
        l.quantity,
        l.buy_date,
        l.buy_broker,
        case
            when l.buy_id is not null       then 'compra'
            when s.ticker like '%.D%'       then 'derechos gratuitos'
            else 'sin compra registrada'
        end                                             as acquisition_type,
        s.ecb_units_per_eur                             as sale_ecb_units_per_eur,
        l.buy_ecb_units_per_eur,
        round(s.amount_eur / s.quantity * l.quantity, 2) as transmission_value_eur,
        round(l.unit_cost_eur * l.quantity, 2)          as acquisition_value_eur,
        round(transmission_value_eur - acquisition_value_eur, 2)
                                                        as gain_loss_eur,
        least(coalesce(w.repurchased_quantity, 0) / s.quantity, 1)
                                                        as repurchased_ratio,
        s.trade_date + interval 2 month > current_date  as two_month_window_open,
        -- a buy dated after the sale means purchase history is missing
        coalesce(l.buy_id is null and s.ticker not like '%.D%'
                 or l.buy_date > s.trade_date, false)   as needs_review
    from lots l
    join sells s on s.trade_id = l.sale_id
    left join two_month_window w on w.sale_id = s.trade_id
)

select
    g.sale_date,
    g.sale_year,
    g.ticker,
    coalesce(m.company_name, g.ticker)                  as company_name,
    m.isin,
    g.sale_broker,
    g.currency,
    g.quantity,
    g.buy_date,
    g.buy_broker,
    g.acquisition_type,
    datediff('day', g.buy_date, g.sale_date)            as holding_days,
    g.sale_ecb_units_per_eur,
    g.buy_ecb_units_per_eur,
    g.transmission_value_eur,
    g.acquisition_value_eur,
    g.gain_loss_eur,
    case when g.gain_loss_eur < 0
        then round(-g.gain_loss_eur * g.repurchased_ratio, 2) else 0
    end                                                 as deferred_loss_eur,
    round(g.gain_loss_eur + deferred_loss_eur, 2)       as computable_gain_loss_eur,
    g.two_month_window_open,
    g.needs_review
from gains g
left join {{ ref('int_ticker_metadata') }} m using (ticker)
where g.sale_date >= cast('{{ var("capital_gains_from") }}' as date)
order by g.sale_date, g.ticker, g.buy_date
