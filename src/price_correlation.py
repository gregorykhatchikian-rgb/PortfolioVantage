"""Phase 6 (stretch): did sentiment shifts precede price moves?

The honest framing matters more than the result here. This asks one narrow
question - when an LLM's read of a company's tone changed between two calls, did
the stock subsequently move in the same direction? - over a sample far too small
to settle it. plan.md is explicit that "no meaningful correlation" is a legitimate
finding, and forcing a signal out of 16 observations would be the kind of claim
that collapses under a single interview question.

Two approximations that limit what any result can mean, both unavoidable with the
data we have:

  1. No call dates. AlphaVantage returns fiscal period labels, not the date the
     call happened. Calls typically land 2-6 weeks after period end, so the call
     is approximated as period_end + 35 days. A few weeks of error at the entry
     point is material for a one-quarter return.
  2. Price data is unadjusted for market direction. A stock that rose while the
     whole index rose tells you about the index, not the earnings call.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from src.trend_aggregator import SeriesPoint

# Calls typically occur a few weeks after the fiscal period closes.
CALL_LAG_DAYS = 35
# Forward window over which to measure the price response - roughly one quarter.
FORWARD_DAYS = 90


@dataclass(frozen=True)
class Observation:
    ticker: str
    from_quarter: str
    to_quarter: str
    delta_sentiment: float
    forward_return: float
    entry: date
    exit: date

    @property
    def agreed(self) -> bool:
        """Did price move the same direction as the sentiment shift?"""
        return (self.delta_sentiment > 0) == (self.forward_return > 0)


def approx_call_date(period_end: date) -> date:
    return period_end + timedelta(days=CALL_LAG_DAYS)


def load_prices(tickers: list[str], start: date, end: date):
    """Daily closes from Yahoo. Returns (DataFrame, error) - never raises.

    yfinance scrapes Yahoo rather than using a supported API (plan.md section 6),
    so a failure here is an expected mode, not a bug in this code.
    """
    try:
        import yfinance as yf

        data = yf.download(tickers, start=start, end=end, progress=False,
                           auto_adjust=True, threads=False)
        if data is None or data.empty:
            return None, "yfinance returned no data (Yahoo may have changed its API)"
        closes = data["Close"] if "Close" in data.columns.get_level_values(0) else data
        return closes, None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def _price_on_or_after(prices, ticker: str, when: date) -> float | None:
    try:
        col = prices[ticker].dropna()
    except (KeyError, TypeError):
        return None
    forward = col[col.index.date >= when]
    return float(forward.iloc[0]) if len(forward) else None


def build_observations(series: dict[str, list[SeriesPoint]], prices) -> list[Observation]:
    """One observation per consecutive pair of calls per ticker."""
    out: list[Observation] = []
    for ticker, points in series.items():
        for older, newer in zip(points, points[1:]):
            entry = approx_call_date(newer.period_end)
            exit_ = entry + timedelta(days=FORWARD_DAYS)
            p0 = _price_on_or_after(prices, ticker, entry)
            p1 = _price_on_or_after(prices, ticker, exit_)
            if p0 is None or p1 is None or p0 == 0:
                continue
            out.append(Observation(
                ticker=ticker,
                from_quarter=older.quarter,
                to_quarter=newer.quarter,
                delta_sentiment=newer.sentiment_score - older.sentiment_score,
                forward_return=(p1 - p0) / p0,
                entry=entry,
                exit=exit_,
            ))
    return out


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Correlation coefficient, or None when it is undefined (zero variance)."""
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None  # a constant has no correlation with anything
    return sxy / (sxx * syy) ** 0.5


def t_statistic(r: float, n: int) -> float | None:
    if n < 3 or abs(r) >= 1:
        return None
    return r * ((n - 2) / (1 - r * r)) ** 0.5
