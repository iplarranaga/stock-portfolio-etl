-- One ECB reference rate per currency per calendar day, for converting
-- foreign-currency amounts to euros in the tax models.
-- The ECB publishes only on TARGET business days; weekends and holidays take
-- the last rate published before them. EUR is included with rate 1.
with rates as (
    select
        cast(rate_date as date)             as rate_date,
        currency,
        cast(units_per_eur as double)       as units_per_eur
    from {{ source('ecb', 'ecb_fx_rates') }}
),

calendar as (
    select cast(d as date) as rate_date
    from generate_series(
        (select min(rate_date) from rates), current_date, interval 1 day
    ) t(d)
),

daily as (
    select c.rate_date, r.currency, r.units_per_eur, r.rate_date as published_date
    from calendar c
    cross join (select distinct currency from rates) ccy
    asof join rates r
        on r.currency = ccy.currency and r.rate_date <= c.rate_date
)

select rate_date, currency, units_per_eur, published_date from daily
union all
select rate_date, 'EUR', 1.0, rate_date from calendar
