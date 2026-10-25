-- Annual dividend tax report, one row per year × ticker × currency × broker.
-- All amounts in euros at the ECB rate on the pay date (*_eur in fct_dividends).
-- Country comes from ticker_metadata (via fct_dividends); expected rates from
-- the country_withholding_rates seed.
--
-- Withholding is split for the Spanish return:
--   foreign_withholding  — tax withheld at origin (casilla de doble imposición)
--   spanish_withholding  — Spain's 19% retención (pagos a cuenta)
-- Broker A withholds origin tax only. Broker B withholds both and reports only the
-- total, so its origin part is estimated at the treaty rate from the seed.
with dividends as (
    select * from {{ ref('fct_dividends') }}
),

rates as (
    select * from {{ ref('country_withholding_rates') }}
),

split as (
    select
        d.*,
        r.country_name,
        coalesce(r.withholding_rate_pct, 0)             as expected_withholding_rate_pct,
        case
            when d.country_code = 'ES'  then 0
            when d.broker = 'Broker B'  then least(
                                                d.gross_amount_eur * coalesce(r.withholding_rate_pct, 0) / 100,
                                                d.withholding_tax_eur)
            else d.withholding_tax_eur
        end                                             as foreign_withholding_eur
    from dividends d
    left join rates r using (country_code)
),

aggregated as (
    select
        dividend_year,
        country_code,
        country_name,
        ticker,
        currency,
        broker,
        expected_withholding_rate_pct,
        sum(gross_amount_eur)                           as gross_dividends_eur,
        sum(withholding_tax_eur)                        as withholding_tax_eur,
        round(sum(foreign_withholding_eur), 2)          as foreign_withholding_eur,
        round(sum(withholding_tax_eur - foreign_withholding_eur), 2)
                                                        as spanish_withholding_eur,
        sum(net_amount_eur)                             as net_dividends_eur
    from split
    group by all
)

select
    dividend_year,
    country_code,
    country_name,
    ticker,
    currency,
    broker,
    gross_dividends_eur,
    withholding_tax_eur,
    foreign_withholding_eur,
    spanish_withholding_eur,
    net_dividends_eur,
    -- Rate withheld by the issuer's country (Spain's own 19% for ES issuers),
    -- compared against the seed's expected rate for that country.
    case
        when gross_dividends_eur > 0
            then round(
                case when country_code = 'ES' then spanish_withholding_eur
                     else foreign_withholding_eur end
                    / gross_dividends_eur * 100,
                2)
    end                                                 as effective_withholding_rate_pct,
    expected_withholding_rate_pct,
    effective_withholding_rate_pct
        - expected_withholding_rate_pct                 as withholding_rate_variance_pct
from aggregated
order by dividend_year desc, gross_dividends_eur desc
