"""
Cartera Dividendos — Streamlit dashboard.
Run from the repo root:
    streamlit run app.py
    CARTERA_DB_PATH=database/sample_data.db streamlit run app.py   # demo data
"""

import os

import duckdb
import plotly.express as px
import streamlit as st

DB_PATH = os.environ.get("CARTERA_DB_PATH", "database/cartera.db")

st.set_page_config(
    page_title="Cartera Dividendos",
    page_icon="📈",
    layout="wide",
)


@st.cache_resource
def get_conn() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(DB_PATH, read_only=True)


def query(sql: str) -> "pd.DataFrame":
    return get_conn().execute(sql).df()


# ── Year range ────────────────────────────────────────────────────────────────
years_df = query("SELECT min(year(pay_date)) AS mn, max(year(pay_date)) AS mx FROM main_marts.fct_dividends")
y_min_db = int(years_df["mn"].iloc[0])
y_max_db = int(years_df["mx"].iloc[0])

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Cartera Dividendos")
    st.markdown("---")

    year_range = st.slider(
        "Year range",
        min_value=y_min_db,
        max_value=y_max_db,
        value=(y_min_db, y_max_db),
    )
    y_min, y_max = year_range

    broker_choice = st.selectbox("Broker", ["All", "Broker A", "Broker B", "Broker C"])
    broker_filter = f"AND broker = '{broker_choice}'" if broker_choice != "All" else ""

    st.markdown("---")
    st.caption("Data from DuckDB · dbt models")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_div, tab_pos, tab_hist = st.tabs(["💰 Dividend Income", "📊 Portfolio Positions", "📋 History"])

# ══════════════════════════════════════════════════════════════════════════════
# Tab 1 — Dividend Income
# ══════════════════════════════════════════════════════════════════════════════
with tab_div:
    monthly_df = query(f"""
        SELECT
            date_trunc('month', pay_date)::date                             AS month,
            broker,
            sum(coalesce(gross_amount_base, net_amount_base))::double       AS gross_eur,
            sum(coalesce(withholding_tax_base, 0))::double                  AS tax_eur,
            sum(net_amount_base)::double                                     AS net_eur,
            count(*)                                                         AS payments
        FROM main_marts.fct_dividends
        WHERE (gross_amount > 0 OR gross_amount IS NULL)
          AND year(pay_date) BETWEEN {y_min} AND {y_max}
          {broker_filter}
        GROUP BY 1, 2
        ORDER BY 1
    """)

    # KPI cards
    total_gross = monthly_df["gross_eur"].sum()
    total_tax   = monthly_df["tax_eur"].sum()
    total_net   = monthly_df["net_eur"].sum()
    total_pmts  = int(monthly_df["payments"].sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Gross dividends", f"€ {total_gross:,.2f}")
    c2.metric("Withholding tax", f"€ {total_tax:,.2f}")
    c3.metric("Net received", f"€ {total_net:,.2f}")
    c4.metric("Payments", total_pmts)

    st.markdown("### Monthly net income")

    if monthly_df.empty:
        st.info("No dividend data for the selected filters.")
    else:
        broker_colors = {"Broker A": "#1f77b4", "Broker B": "#ff7f0e", "Broker C": "#2ca02c"}
        fig = px.bar(
            monthly_df,
            x="month",
            y="net_eur",
            color="broker",
            barmode="stack",
            color_discrete_map=broker_colors,
            labels={"month": "", "net_eur": "Net (€)", "broker": "Broker"},
            height=380,
        )
        fig.update_layout(
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(t=20, b=0),
            hovermode="x unified",
        )
        fig.update_traces(hovertemplate="%{y:.2f} €")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Annual net income")

    if monthly_df.empty:
        st.info("No dividend data for the selected filters.")
    else:
        yearly_df = monthly_df.assign(year=monthly_df["month"].apply(lambda d: d.year)) \
            .groupby(["year", "broker"], as_index=False)["net_eur"].sum()
        broker_colors = {"Broker A": "#1f77b4", "Broker B": "#ff7f0e", "Broker C": "#2ca02c"}
        fig_year = px.bar(
            yearly_df,
            x="year",
            y="net_eur",
            color="broker",
            barmode="stack",
            color_discrete_map=broker_colors,
            labels={"year": "", "net_eur": "Net (€)", "broker": "Broker"},
            height=320,
        )
        fig_year.update_layout(
            xaxis=dict(type="category"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(t=20, b=0),
            hovermode="x unified",
        )
        fig_year.update_traces(hovertemplate="%{y:.2f} €")
        st.plotly_chart(fig_year, use_container_width=True)

    # Annual summary table
    st.markdown("### Annual summary")
    annual_df = query(f"""
        SELECT
            year(pay_date)                                                   AS year,
            count(*)                                                         AS payments,
            round(sum(coalesce(gross_amount_base, net_amount_base))::double, 2) AS gross_eur,
            round(sum(coalesce(withholding_tax_base, 0))::double, 2)         AS tax_eur,
            round(sum(net_amount_base)::double, 2)                           AS net_eur
        FROM main_marts.fct_dividends
        WHERE (gross_amount > 0 OR gross_amount IS NULL)
          AND year(pay_date) BETWEEN {y_min} AND {y_max}
          {broker_filter}
        GROUP BY 1
        ORDER BY 1
    """)
    st.dataframe(
        annual_df.rename(columns={
            "year": "Year", "payments": "Payments",
            "gross_eur": "Gross (€)", "tax_eur": "Tax (€)", "net_eur": "Net (€)",
        }),
        use_container_width=True,
        hide_index=True,
    )

    # Dividend pies by sector and company
    st.markdown("### Breakdown")
    div_pie_df = query(f"""
        SELECT
            coalesce(sector, 'Unknown')     AS sector,
            company_name,
            round(sum(net_amount_base)::double, 2) AS net_eur
        FROM main_marts.fct_dividends
        WHERE (gross_amount > 0 OR gross_amount IS NULL)
          AND year(pay_date) BETWEEN {y_min} AND {y_max}
          {broker_filter}
        GROUP BY 1, 2
        ORDER BY net_eur DESC
    """)

    if not div_pie_df.empty:
        st.download_button(
            "⬇️ Download CSV (company, sector, dividends)",
            data=div_pie_df.rename(columns={
                "sector": "Sector", "company_name": "Company", "net_eur": "Net Dividends (€)",
            }).to_csv(index=False).encode("utf-8"),
            file_name=f"dividend_distribution_{y_min}_{y_max}.csv",
            mime="text/csv",
        )

        pc1, pc2 = st.columns(2)
        with pc1:
            fig_ds = px.pie(
                div_pie_df.groupby("sector", as_index=False)["net_eur"].sum(),
                values="net_eur", names="sector",
                title="Net income by sector", hole=0.35,
            )
            fig_ds.update_traces(textposition="inside", textinfo="percent+label")
            fig_ds.update_layout(showlegend=False, margin=dict(t=40, b=0))
            st.plotly_chart(fig_ds, use_container_width=True)
        with pc2:
            fig_dc = px.pie(
                div_pie_df,
                values="net_eur", names="company_name",
                title="Net income by company", hole=0.35,
            )
            fig_dc.update_traces(textposition="inside", textinfo="percent+label")
            fig_dc.update_layout(showlegend=False, margin=dict(t=40, b=0))
            st.plotly_chart(fig_dc, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Portfolio Positions
# ══════════════════════════════════════════════════════════════════════════════
with tab_pos:
    pos_df = query(f"""
        SELECT
            ticker,
            company_name,
            sector,
            broker,
            quantity::double                    AS quantity,
            round(avg_cost_price_base, 2)        AS avg_cost_eur,
            round(cost_basis_base::double, 2)    AS cost_basis_eur,
            last_trade_date
        FROM main_marts.fct_positions
        WHERE 1=1 {broker_filter}
        ORDER BY cost_basis_base DESC
    """)

    total_invested = pos_df["cost_basis_eur"].sum()
    n_positions = pos_df["ticker"].nunique()

    c1, c2 = st.columns(2)
    c1.metric("Total invested", f"€ {total_invested:,.2f}")
    c2.metric("Open positions", n_positions)

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown("### Holdings")
        st.dataframe(
            pos_df.rename(columns={
                "ticker": "Ticker", "company_name": "Company", "sector": "Sector",
                "broker": "Broker", "quantity": "Qty", "avg_cost_eur": "Avg Cost (€)",
                "cost_basis_eur": "Cost Basis (€)", "last_trade_date": "Last Trade",
            }),
            use_container_width=True,
            hide_index=True,
        )

    with col_right:
        st.markdown("### Cost basis by ticker")
        if pos_df.empty:
            st.info("No positions for the selected filters.")
        else:
            broker_colors = {"Broker A": "#1f77b4", "Broker B": "#ff7f0e", "Broker C": "#2ca02c"}
            fig2 = px.bar(
                pos_df.sort_values("cost_basis_eur"),
                x="cost_basis_eur",
                y="ticker",
                color="broker",
                orientation="h",
                color_discrete_map=broker_colors,
                labels={"cost_basis_eur": "Cost Basis (€)", "ticker": "", "broker": "Broker"},
                height=max(380, n_positions * 22),
            )
            fig2.update_layout(
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                margin=dict(t=20, l=0),
                yaxis={"categoryorder": "total ascending"},
            )
            fig2.update_traces(hovertemplate="%{x:.2f} €")
            st.plotly_chart(fig2, use_container_width=True)

    # Portfolio pies by sector and company
    if not pos_df.empty:
        st.markdown("### Breakdown")
        pie_col1, pie_col2 = st.columns(2)
        with pie_col1:
            fig_sec = px.pie(
                pos_df.groupby("sector", as_index=False)["cost_basis_eur"].sum(),
                values="cost_basis_eur", names="sector",
                title="Cost basis by sector", hole=0.35,
            )
            fig_sec.update_traces(textposition="inside", textinfo="percent+label")
            fig_sec.update_layout(showlegend=False, margin=dict(t=40, b=0))
            st.plotly_chart(fig_sec, use_container_width=True)
        with pie_col2:
            fig_co = px.pie(
                pos_df.groupby("company_name", as_index=False)["cost_basis_eur"].sum(),
                values="cost_basis_eur", names="company_name",
                title="Cost basis by company", hole=0.35,
            )
            fig_co.update_traces(textposition="inside", textinfo="percent+label")
            fig_co.update_layout(showlegend=False, margin=dict(t=40, b=0))
            st.plotly_chart(fig_co, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# Tab 3 — History
# ══════════════════════════════════════════════════════════════════════════════
with tab_hist:
    h_ops, h_div = st.tabs(["🔄 Operations", "💵 Dividends"])

    # ── Operations history ────────────────────────────────────────────────────
    with h_ops:
        ops_df = query(f"""
            SELECT
                trade_date                              AS date,
                ticker,
                broker,
                side,
                abs(quantity)::double                   AS quantity,
                round(abs(price)::double, 4)            AS price,
                round(abs(net_cash)::double, 2)         AS amount_eur,
                currency
            FROM main_intermediate.int_trades
            WHERE year(trade_date) BETWEEN {y_min} AND {y_max}
              {broker_filter}
            ORDER BY trade_date DESC
        """)

        c1, c2, c3 = st.columns(3)
        c1.metric("Total operations", len(ops_df))
        buys  = ops_df[ops_df["side"] == "BUY"]["amount_eur"].sum()
        sells = ops_df[ops_df["side"] == "SELL"]["amount_eur"].sum()
        c2.metric("Total bought", f"€ {buys:,.2f}")
        c3.metric("Total sold",   f"€ {sells:,.2f}")

        st.dataframe(
            ops_df.rename(columns={
                "date": "Date", "ticker": "Ticker", "broker": "Broker",
                "side": "Side", "quantity": "Qty", "price": "Price",
                "amount_eur": "Amount (€)", "currency": "CCY",
            }),
            use_container_width=True,
            hide_index=True,
        )

        # ── Aggregated purchases by ticker ──────────────────────────────────
        st.markdown("### Aggregated by ticker (purchases)")
        agg_df = query(f"""
            WITH held AS (
                -- Currently open positions only (all-time, ignores year filter)
                SELECT ticker
                FROM main_intermediate.int_trades
                WHERE ticker NOT LIKE '%.D%'   -- exclude scrip-dividend rights
                  {broker_filter}
                GROUP BY 1
                HAVING sum(case when side = 'BUY' then quantity else 0 end)
                     + sum(case when side = 'SELL' then quantity else 0 end) > 0
            ),
            buys AS (
                SELECT ticker, quantity, net_cash_base, trade_date
                FROM main_intermediate.int_trades
                WHERE side = 'BUY'
                  AND year(trade_date) BETWEEN {y_min} AND {y_max}
                  {broker_filter}
            )
            SELECT
                b.ticker,
                coalesce(m.company_name, b.ticker)  AS company,
                count(*)                            AS num_purchases,
                sum(abs(b.quantity))::double         AS shares,
                sum(abs(b.net_cash_base))::double    AS cost_eur,
                max(b.trade_date)                    AS last_purchase_date
            FROM buys b
            JOIN held h ON h.ticker = b.ticker
            LEFT JOIN main_staging.stg_ticker_metadata m ON m.ticker = b.ticker
            GROUP BY 1, 2
            ORDER BY cost_eur DESC
        """)

        if agg_df.empty:
            st.info("No purchase data for the selected filters.")
        else:
            total_cost = agg_df["cost_eur"].sum()
            agg_df["weight_pct"] = (agg_df["cost_eur"] / total_cost * 100).round(2)
            agg_df["cost_eur"] = agg_df["cost_eur"].round(2)

            display_df = agg_df.rename(columns={
                "ticker": "Ticker", "company": "Company",
                "num_purchases": "# Purchases", "weight_pct": "Weight (%)",
                "shares": "Shares", "last_purchase_date": "Last Purchase",
            })[["Ticker", "Company", "# Purchases", "Weight (%)", "Shares", "Last Purchase"]]

            st.download_button(
                "⬇️ Download CSV (aggregated purchases by ticker)",
                data=display_df.to_csv(index=False, sep=";", decimal=",").encode("utf-8"),
                file_name=f"purchases_by_ticker_{y_min}_{y_max}.csv",
                mime="text/csv",
            )

            st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ── Dividends history ─────────────────────────────────────────────────────
    with h_div:
        div_df = query(f"""
            SELECT
                pay_date                                                        AS date,
                ticker,
                broker,
                currency,
                round(coalesce(gross_amount, net_amount)::double, 4)            AS gross,
                round(coalesce(withholding_tax, 0)::double, 4)                  AS tax,
                round(net_amount::double, 4)                                     AS net,
                round(net_amount_base::double, 2)                               AS net_eur,
                coalesce(effective_withholding_rate_pct::double, 0)             AS whd_rate_pct
            FROM main_marts.fct_dividends
            WHERE (gross_amount > 0 OR gross_amount IS NULL)
              AND year(pay_date) BETWEEN {y_min} AND {y_max}
              {broker_filter}
            ORDER BY pay_date DESC
        """)

        c1, c2, c3 = st.columns(3)
        c1.metric("Dividend payments", len(div_df))
        c2.metric("Total net (€)", f"€ {div_df['net_eur'].sum():,.2f}")
        avg_wh = div_df[div_df["whd_rate_pct"] > 0]["whd_rate_pct"].mean()
        c3.metric("Avg withholding", f"{avg_wh:.1f} %" if not __import__('math').isnan(avg_wh) else "—")

        st.dataframe(
            div_df.rename(columns={
                "date": "Date", "ticker": "Ticker", "broker": "Broker",
                "currency": "CCY", "gross": "Gross", "tax": "Tax",
                "net": "Net", "net_eur": "Net (€)", "whd_rate_pct": "WHD %",
            }),
            use_container_width=True,
            hide_index=True,
        )
