-- Broker B reports net dividends (after origin withholding and Spain's 19% retención).
-- Gross is derived as titulos × precio (dividend per share, already in EUR);
-- withholding_tax is everything withheld (origin + Spanish) = gross - net.
-- valor (company name) is resolved to a canonical ticker via ticker_metadata.
-- The loader reads every export in data/broker_b/ and their date ranges overlap, so
-- identical rows are numbered within each file and one row is kept per
-- (row, occurrence): overlaps collapse, genuine same-day repeats survive.
with numbered as (
    select
        *,
        row_number() over (
            partition by source_file, fecha, operacion, valor, titulos,
                         precio_en_divisa_origen, importe_total_eur
        ) as occurrence
    from {{ source('broker_b', 'broker_b_dividends') }}
),

source as (
    select * exclude (occurrence)
    from numbered
    qualify row_number() over (
        partition by fecha, operacion, valor, titulos,
                     precio_en_divisa_origen, importe_total_eur, occurrence
        order by source_file desc
    ) = 1
),

renamed as (
    select
        strptime(source.fecha, '%d/%m/%Y')::date               as pay_date,
        coalesce(tm.canonical_ticker, source.valor)            as ticker,
        cast(source.titulos as integer)                        as quantity,
        cast(source.precio_en_divisa_origen as decimal(18, 6)) as price_per_share,
        cast(source.importe_total_eur as decimal(18, 4))       as net_amount,
        round(cast(source.titulos as integer)
            * cast(source.precio_en_divisa_origen as decimal(18, 6)), 2)::decimal(18, 4)
                                                               as gross_amount,
        (gross_amount - net_amount)::decimal(18, 4)            as withholding_tax,
        'EUR'                                                  as currency,
        1.0::decimal(18, 6)                                    as fx_rate_to_base,
        net_amount                                             as net_amount_base,
        gross_amount                                           as gross_amount_base,
        withholding_tax                                        as withholding_tax_base,
        source.source_file,
        'Broker B'                                             as broker
    from source
    left join {{ ref('stg_ticker_metadata') }} tm on tm.ticker = source.valor
)

select * from renamed
