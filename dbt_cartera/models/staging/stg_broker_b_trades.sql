-- OPERACIÓN values: COMPRA (buy) / VENTA (sell)
-- importe_total_eur is always positive in Broker B exports; negate for BUY so that
-- net_cash follows the convention: negative = money out (buy), positive = money in (sell).
-- valor (company name) is resolved to a canonical ticker via ticker_metadata.
-- Overlapping exports are collapsed the same way as in stg_broker_b_dividends.
with numbered as (
    select
        *,
        row_number() over (
            partition by source_file, fecha, operacion, valor, titulos,
                         precio_en_divisa_origen, importe_total_eur
        ) as occurrence
    from {{ source('broker_b', 'broker_b_trades') }}
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
        strptime(source.fecha, '%d/%m/%Y')::date                        as trade_date,
        coalesce(tm.canonical_ticker, source.valor)                     as ticker,
        case source.operacion
            when 'COMPRA' then  cast(source.titulos as integer)
            when 'VENTA'  then -cast(source.titulos as integer)
            else               cast(source.titulos as integer)
        end                                                             as quantity,
        cast(source.precio_en_divisa_origen as decimal(18, 6))          as price,
        case source.operacion
            when 'COMPRA' then -cast(source.importe_total_eur as decimal(18, 4))
            when 'VENTA'  then  cast(source.importe_total_eur as decimal(18, 4))
            else                cast(source.importe_total_eur as decimal(18, 4))
        end                                                             as net_cash,
        case source.operacion
            when 'COMPRA' then 'BUY'
            when 'VENTA'  then 'SELL'
            else source.operacion
        end                                                             as side,
        'EUR'                                                           as currency,
        1.0::decimal(18, 6)                                             as fx_rate_to_base,
        case source.operacion
            when 'COMPRA' then -cast(source.importe_total_eur as decimal(18, 4))
            when 'VENTA'  then  cast(source.importe_total_eur as decimal(18, 4))
            else                cast(source.importe_total_eur as decimal(18, 4))
        end                                                             as net_cash_base,
        source.source_file,
        'Broker B'                                                      as broker
    from source
    left join {{ ref('stg_ticker_metadata') }} tm on tm.ticker = source.valor
)

select * from renamed
