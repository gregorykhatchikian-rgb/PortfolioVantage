"""Phase 4: turn per-call extractions into per-ticker time series and portfolio themes.

The problem this module exists to solve is that the provider labels transcripts by
each company's OWN fiscal calendar. "2026Q2" is Jan-Mar for Apple, May-Jul 2025 for
NVIDIA, and Apr-Jun 2026 for JPMorgan. Sorting or charting on that label would put
points up to a year apart on the same tick - see plan.md section 6.

So every quarter label is converted to the calendar month its period actually ended,
and everything downstream orders by that date rather than by the label.
"""

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date

from src import config

EXTRACTION_DIR = config.DATA_DIR / "extractions"

# Month in which each company's FISCAL year ends. Maintained by hand: the provider
# gives no period-end date, so this can't be derived from the data. Tickers absent
# here are assumed to be on the calendar year, which build_series() reports rather
# than applying silently.
FISCAL_YEAR_END_MONTH = {
    "AAPL": 9,   # late September
    "MSFT": 6,   # June 30
    "NVDA": 1,   # late January
    "CRM": 1,    # January 31
    "PG": 6,     # June 30
    "JPM": 12,
    "XOM": 12,
    "TSLA": 12,
}
DEFAULT_FY_END_MONTH = 12

QUARTER_RE = re.compile(r"^(\d{4})Q([1-4])$")


@dataclass(frozen=True)
class SeriesPoint:
    ticker: str
    quarter: str          # provider label, e.g. "2026Q2"
    period_end: date      # calendar month the fiscal period actually ended
    sentiment_score: float
    sentiment_label: str
    themes: tuple[str, ...]
    notable_shift: str
    confidence: str
    source_file: str      # provenance: which extraction produced this point


def period_end(ticker: str, quarter_label: str) -> date:
    """Calendar month-end that a company's fiscal quarter label corresponds to.

    Fiscal year Y ends in month M of calendar year Y, so quarter q ends 3*(4-q)
    months earlier, rolling back into the previous calendar year where needed.
    """
    m = QUARTER_RE.match(quarter_label)
    if not m:
        raise ValueError(f"unrecognised quarter label: {quarter_label!r}")
    fiscal_year, q = int(m.group(1)), int(m.group(2))

    month = FISCAL_YEAR_END_MONTH.get(ticker.upper(), DEFAULT_FY_END_MONTH) - 3 * (4 - q)
    year = fiscal_year
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def uses_default_calendar(ticker: str) -> bool:
    return ticker.upper() not in FISCAL_YEAR_END_MONTH


def load_extractions() -> list[SeriesPoint]:
    """Read every extraction JSON into a SeriesPoint, ordered by ticker then date."""
    points: list[SeriesPoint] = []
    for path in sorted(EXTRACTION_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        points.append(SeriesPoint(
            ticker=data["ticker"],
            quarter=data["quarter"],
            period_end=period_end(data["ticker"], data["quarter"]),
            sentiment_score=float(data["sentiment_score"]),
            sentiment_label=data["sentiment_label"],
            themes=tuple(data["themes"]),
            notable_shift=data["notable_shift"],
            confidence=data["confidence"],
            source_file=path.name,
        ))
    return sorted(points, key=lambda p: (p.ticker, p.period_end))


def build_series(points: list[SeriesPoint]) -> dict[str, list[SeriesPoint]]:
    """Per-ticker series in true chronological order."""
    series: dict[str, list[SeriesPoint]] = defaultdict(list)
    for p in points:
        series[p.ticker].append(p)
    return {t: sorted(ps, key=lambda p: p.period_end) for t, ps in series.items()}


def theme_frequency(points: list[SeriesPoint]) -> list[tuple[str, int, int]]:
    """(theme, total mentions, distinct tickers), most cross-cutting first.

    Distinct-ticker count is the signal that matters: a theme one company repeats
    three times is that company's story, whereas one appearing across five holdings
    is a portfolio-level trend.
    """
    total: Counter[str] = Counter()
    tickers: defaultdict[str, set[str]] = defaultdict(set)
    for p in points:
        for theme in p.themes:
            total[theme] += 1
            tickers[theme].add(p.ticker)
    return sorted(
        ((t, total[t], len(tickers[t])) for t in total),
        key=lambda x: (-x[2], -x[1], x[0]),
    )


def keyword_frequency(points: list[SeriesPoint], min_len: int = 3) -> list[tuple[str, int]]:
    """Theme frequency at the word level.

    Exact theme strings rarely repeat across companies - "ai capex", "ai investments"
    and "ai infrastructure growth" are three distinct strings describing one trend -
    so exact matching alone would make a cross-portfolio heatmap look empty.
    """
    stop = {"and", "the", "for", "with", "growth", "strong"}
    counts: defaultdict[str, set[str]] = defaultdict(set)
    for p in points:
        for theme in p.themes:
            for word in re.findall(r"[a-z]+", theme.lower()):
                if len(word) >= min_len and word not in stop:
                    counts[word].add(p.ticker)
    return sorted(((w, len(ts)) for w, ts in counts.items()), key=lambda x: (-x[1], x[0]))


def consecutive_declines(series: list[SeriesPoint]) -> int:
    """How many consecutive quarter-over-quarter declines end the series.

    plan.md Phase 5 defines the watch-list flag as 2+ consecutive declines. Note
    this counts direction only, not magnitude: a -0.05 drift counts the same as
    -0.40. Whether a decline is larger than this pipeline's run-to-run noise is a
    separate question, and callers should surface it rather than imply precision.
    """
    if len(series) < 2:
        return 0
    count = 0
    for older, newer in zip(reversed(series[:-1]), reversed(series)):
        if newer.sentiment_score < older.sentiment_score:
            count += 1
        else:
            break
    return count


def total_change(series: list[SeriesPoint]) -> float:
    return series[-1].sentiment_score - series[0].sentiment_score if len(series) > 1 else 0.0


def theme_matrix(points: list[SeriesPoint], top_n: int = 12):
    """Theme x ticker counts as a DataFrame, for the portfolio heatmap."""
    import pandas as pd

    rows = theme_frequency(points)[:top_n]
    themes = [r[0] for r in rows]
    tickers = sorted({p.ticker for p in points})
    grid = {tk: [sum(1 for p in points if p.ticker == tk and th in p.themes) for th in themes]
            for tk in tickers}
    return pd.DataFrame(grid, index=themes)
