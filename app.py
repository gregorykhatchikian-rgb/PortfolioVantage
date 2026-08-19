"""Phase 5: Streamlit dashboard over the Phase 4 trend data.

Reads only from data/extractions - if that directory is empty the app says so
rather than rendering placeholder numbers, since a dashboard showing invented
data is worse than one showing none.
"""

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import config
from src.csv_loader import load_portfolio
from src.trend_aggregator import (
    build_series, consecutive_declines, keyword_frequency, load_extractions,
    theme_matrix, total_change,
)

# Re-scoring the same transcript is deterministic in practice: 9 repeat runs across
# three calls produced identical scores every time (temperature 0.1, extraction task).
# So a movement here reflects the transcripts, not sampling randomness. The real
# limitation is resolution - observed scores take only a handful of distinct values.

st.set_page_config(page_title="Portfolio Earnings Trend Analyzer", layout="wide")


@st.cache_data
def load():
    points = load_extractions()
    portfolio = load_portfolio(config.DATA_DIR / "portfolio.csv")
    return points, portfolio.holdings


points, holdings = load()

st.title("Portfolio Earnings Trend Analyzer")
if not points:
    st.error("No extractions found. Run `python scripts/run_extraction.py` first.")
    st.stop()

series = build_series(points)
st.caption(
    f"{len(points)} earnings calls across {len(series)} holdings. "
    f"Sentiment scored -1 to +1 by an LLM reading each transcript."
)

# --- watch list -------------------------------------------------------------
flagged = [(t, consecutive_declines(ps), total_change(ps))
           for t, ps in series.items() if consecutive_declines(ps) >= 2]

if flagged:
    for ticker, n, delta in sorted(flagged, key=lambda x: x[2]):
        st.error(f"**{ticker}** — sentiment declined {n} consecutive quarters "
                 f"({delta:+.2f} total)")
else:
    st.success("No holding shows 2+ consecutive quarters of declining sentiment.")

# --- holdings table ---------------------------------------------------------
st.subheader("Holdings")
rows = []
for _, h in holdings.iterrows():
    ps = series.get(h["ticker"], [])
    if not ps:
        continue
    delta = total_change(ps)
    rows.append({
        "Ticker": h["ticker"],
        "Shares": int(h["shares"]),
        "Weight": f"{h['weight']:.0%}",
        "Latest": ps[-1].sentiment_score,
        "Label": ps[-1].sentiment_label,
        "Change": delta,
        "Trend": "flat" if abs(delta) < 0.05 else ("up" if delta > 0 else "down"),
        "Confidence": ps[-1].confidence,
    })
st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)

# --- per-holding detail -----------------------------------------------------
st.subheader("Sentiment trend")
choice = st.selectbox("Holding", sorted(series))
chosen = series[choice]

# Altair rather than st.line_chart: the built-in treats period_end as a continuous
# date axis and labels it fortnightly, which is meaningless for quarterly points.
# The y domain is pinned to the real -1..1 scale so a reader can see where a score
# sits in the range, instead of an auto-zoom that makes any wobble look dramatic.
chart_df = pd.DataFrame({
    "period": [f"{p.period_end:%b %Y}" for p in chosen],
    "sentiment": [p.sentiment_score for p in chosen],
    "quarter": [p.quarter for p in chosen],
    "label": [p.sentiment_label for p in chosen],
})
order = list(chart_df["period"])
base = alt.Chart(chart_df).encode(
    x=alt.X("period:N", sort=order, title=None),
    y=alt.Y("sentiment:Q", title="sentiment", scale=alt.Scale(domain=[-1, 1])),
    tooltip=["period", "quarter", "sentiment", "label"],
)
st.altair_chart(
    base.mark_line(color="#4c8bf5", strokeWidth=2)
    + base.mark_point(color="#4c8bf5", size=90, filled=True)
    + alt.Chart(chart_df).mark_rule(color="#555", strokeDash=[4, 4]).encode(y=alt.datum(0)),
    width='stretch',
)
st.caption(
    f"Quarters are plotted by the calendar month each fiscal period ended, not by "
    f"the provider's label — {choice}'s labels map to "
    f"{', '.join(f'{p.quarter}→{p.period_end:%b %Y}' for p in chosen)}."
)

for p in reversed(chosen):
    with st.expander(f"{p.period_end:%b %Y}  ({p.quarter})  ·  "
                     f"{p.sentiment_score:+.2f} {p.sentiment_label}"):
        st.write(f"**Themes:** {', '.join(p.themes)}")
        st.write(f"**Notable shift:** {p.notable_shift}")
        st.caption(f"model confidence: {p.confidence} · source: {p.source_file}")

# --- portfolio themes -------------------------------------------------------
st.subheader("Themes across the portfolio")
left, right = st.columns([3, 2])
with left:
    matrix = theme_matrix(points)
    # Altair rather than Styler.background_gradient: the latter needs matplotlib,
    # which isn't in the plan's stack, and this renders as an actual heatmap.
    long = matrix.reset_index(names="theme").melt(
        id_vars="theme", var_name="ticker", value_name="mentions")
    heat = (
        alt.Chart(long)
        .mark_rect()
        .encode(
            x=alt.X("ticker:N", title=None),
            y=alt.Y("theme:N", title=None, sort=list(matrix.index)),
            color=alt.Color("mentions:Q", title="mentions",
                            scale=alt.Scale(scheme="blues")),
            tooltip=["theme", "ticker", "mentions"],
        )
        .properties(height=320)
    )
    st.altair_chart(heat, width='stretch')
    st.caption("Exact theme strings. Companies rarely phrase a shared trend identically, "
               "so this undercounts genuine overlap.")
with right:
    words = [(w, n) for w, n in keyword_frequency(points)[:10] if n > 1]
    st.dataframe(pd.DataFrame(words, columns=["Keyword", "Holdings mentioning"]),
                 width='stretch', hide_index=True)
    st.caption("Word-level view, which catches 'ai capex' and 'ai adoption' as one trend.")
