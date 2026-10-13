from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "trademarks.duckdb"

st.set_page_config(page_title="EU trade mark filing KPIs", layout="wide")
st.title("EU trade mark filing KPIs")
st.caption(
    "Application counts are distinct trade mark applications. "
    "Nice class counts can include one application in several classes."
)

database_path = Path(
    st.sidebar.text_input("DuckDB database", str(DEFAULT_DATABASE))
).expanduser()
if not database_path.is_file():
    st.info(
        "No DuckDB database found. Load a CSV first using "
        "`load-trademarks path-or-url-to.csv`."
    )
    st.stop()

with duckdb.connect(str(database_path), read_only=True) as connection:
    source_type, loaded_at, input_rows = connection.execute(
        "SELECT source_type, loaded_at, input_rows FROM ingestion_metadata"
    ).fetchone()
    years = connection.execute(
        "SELECT DISTINCT filing_year FROM kpi_filings_per_year ORDER BY filing_year"
    ).fetchall()
    if not years:
        st.warning("The database has no filing years to display.")
        st.stop()
    year_values = [row[0] for row in years]
    selected_year = st.sidebar.selectbox("Filing year", year_values, index=len(year_values) - 1)
    previous_year = selected_year - 1
    annual = connection.execute(
        "SELECT * FROM kpi_filings_per_year WHERE filing_year = ?",
        [selected_year],
    ).fetchdf()
    estonian_share = connection.execute(
        "SELECT * FROM kpi_estonian_share WHERE filing_year = ?",
        [selected_year],
    ).fetchdf()
    growth = connection.execute(
        "SELECT * FROM kpi_year_over_year_growth WHERE filing_year = ?",
        [selected_year],
    ).fetchdf()
    top_classes = connection.execute(
        """
        SELECT nice_class, application_count
        FROM kpi_top_nice_classes
        WHERE filing_year = ?
        ORDER BY application_count DESC, nice_class
        LIMIT 10
        """,
        [selected_year],
    ).fetchdf()
    filing_types = connection.execute(
        """
        SELECT filing_type, application_count
        FROM kpi_filing_type_split
        WHERE filing_year = ?
        ORDER BY application_count DESC
        """,
        [selected_year],
    ).fetchdf()
    checks = connection.execute(
        "SELECT check_name, severity, issue_count FROM data_quality_checks"
    ).fetchdf()
    trend = connection.execute(
        "SELECT filing_year, application_count FROM kpi_filings_per_year ORDER BY filing_year"
    ).fetchdf()

if source_type == "synthetic_sample":
    st.warning(
        "Synthetic demo data is loaded. These figures are for testing only and "
        "must not be presented as actual EUIPO statistics."
    )
st.caption(f"Dataset type: {source_type} | Last loaded: {loaded_at} | Input rows: {input_rows:,}")

count = int(annual.iloc[0]["application_count"])
share = float(estonian_share.iloc[0]["estonian_share"])
growth_value = growth.iloc[0]["yoy_growth"]
previous_count = growth.iloc[0]["previous_year_count"]

col1, col2, col3 = st.columns(3)
col1.metric("Applications", f"{count:,}")
col2.metric("Estonian applicant share", f"{share:.1%}")
if pd.isna(growth_value) or pd.isna(previous_count):
    col3.metric("Year-over-year growth", "N/A")
else:
    col3.metric(
        "Year-over-year growth",
        f"{growth_value:+.1%}",
        help=f"Compared with {int(previous_year)} ({int(previous_count):,} applications).",
    )

left, right = st.columns(2)
with left:
    st.subheader("Applications by filing year")
    st.line_chart(trend.set_index("filing_year"))
with right:
    st.subheader("Top Nice classes")
    st.bar_chart(top_classes.set_index("nice_class"))

left, right = st.columns(2)
with left:
    st.subheader("Filing type split")
    st.bar_chart(filing_types.set_index("filing_type"))
with right:
    st.subheader("Data quality checks")
    st.dataframe(checks, hide_index=True, use_container_width=True)
