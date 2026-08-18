"""Phase 2: fetch earnings call transcripts, with a local cache in front of the API.

Source is AlphaVantage's EARNINGS_CALL_TRANSCRIPT endpoint. The free tier allows
roughly 25 requests/day, and one full portfolio run costs tickers x quarters calls,
so the cache is not an optimisation here - without it a second run in the same day
fails outright.

Two AlphaVantage behaviours worth knowing, both handled below:
  - Rate limiting arrives as HTTP 200 with a "Note"/"Information" body, not a 429.
    Checking status codes alone would read a throttle message as a valid transcript.
  - An unknown symbol/quarter combination returns 200 with an empty transcript list
    rather than a 404. That's the "no coverage" case, not an error.
"""

import json
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import requests

from src import config

API_URL = "https://www.alphavantage.co/query"
CACHE_DIR = config.DATA_DIR / "cache" / "transcripts"

# Free tier is throttled per minute as well as per day; a small gap between calls
# keeps a normal run from tripping it. Not a retry loop - see RateLimitedError.
MIN_SECONDS_BETWEEN_CALLS = 1.0


class RateLimitedError(RuntimeError):
    """AlphaVantage signalled a quota limit. Stop the run - do not retry in a loop."""


class TranscriptAPIError(RuntimeError):
    """The API returned something we can't interpret as a transcript or an absence."""


@dataclass(frozen=True)
class Transcript:
    ticker: str
    quarter: str  # AlphaVantage form, e.g. "2026Q2"
    segments: list[dict]
    from_cache: bool = False

    @property
    def raw_text(self) -> str:
        """Flattened 'Speaker (Title): content' text - what Phase 3 sends to the LLM."""
        parts = []
        for seg in self.segments:
            who = seg.get("speaker", "Unknown")
            title = seg.get("title", "")
            head = f"{who} ({title})" if title else who
            parts.append(f"{head}: {seg.get('content', '')}")
        return "\n\n".join(parts)

    @property
    def word_count(self) -> int:
        return sum(len(str(seg.get("content", "")).split()) for seg in self.segments)


@dataclass
class FetchResult:
    transcripts: list[Transcript] = field(default_factory=list)
    missing: list[tuple[str, str]] = field(default_factory=list)  # (ticker, quarter)
    api_calls: int = 0

    def for_ticker(self, ticker: str) -> list[Transcript]:
        return [t for t in self.transcripts if t.ticker == ticker]

    def tickers_with_no_coverage(self, tickers: list[str]) -> list[str]:
        """Tickers where not a single quarter came back with any content."""
        return [t for t in tickers if not any(x.word_count > 0 for x in self.for_ticker(t))]


def recent_quarters(n: int = 3, today: date | None = None) -> list[str]:
    """The last n *completed* calendar quarters, most recent first.

    Note the plan.md section 6 pitfall: fiscal quarters don't always line up with
    calendar ones, so a company's "Q2" may be labelled differently by the provider.
    We record whatever label the API returns rather than trusting our own guess.
    """
    today = today or date.today()
    q = (today.month - 1) // 3 + 1  # quarter currently in progress
    year = today.year
    out = []
    for _ in range(n):
        q -= 1
        if q == 0:
            q, year = 4, year - 1
        out.append(f"{year}Q{q}")
    return out


def _cache_path(ticker: str, quarter: str) -> Path:
    return CACHE_DIR / f"{ticker.upper()}_{quarter}.json"


def _read_cache(ticker: str, quarter: str) -> list[dict] | None:
    path = _cache_path(ticker, quarter)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        path.unlink()  # corrupt cache entry, refetch rather than crash
        return None


def _write_cache(ticker: str, quarter: str, segments: list[dict]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(ticker, quarter).write_text(json.dumps(segments, indent=1))


def _call_api(ticker: str, quarter: str, api_key: str) -> list[dict]:
    resp = requests.get(
        API_URL,
        params={
            "function": "EARNINGS_CALL_TRANSCRIPT",
            "symbol": ticker,
            "quarter": quarter,
            "apikey": api_key,
        },
        timeout=30,
    )
    if resp.status_code == 429:
        raise RateLimitedError(f"HTTP 429 fetching {ticker} {quarter}")
    if resp.status_code != 200:
        raise TranscriptAPIError(f"HTTP {resp.status_code} fetching {ticker} {quarter}")

    try:
        payload = resp.json()
    except ValueError as exc:
        raise TranscriptAPIError(f"non-JSON response for {ticker} {quarter}") from exc

    # Throttle and quota messages come back as HTTP 200. Catch them explicitly.
    for key in ("Note", "Information"):
        if key in payload:
            raise RateLimitedError(f"AlphaVantage quota message: {payload[key]}")
    if "Error Message" in payload:
        raise TranscriptAPIError(f"{ticker} {quarter}: {payload['Error Message']}")

    segments = payload.get("transcript", [])
    if not isinstance(segments, list):
        raise TranscriptAPIError(f"unexpected transcript shape for {ticker} {quarter}")
    return segments


def fetch_transcripts(
    tickers: list[str],
    quarters: list[str] | None = None,
    api_key: str | None = None,
    use_cache: bool = True,
) -> FetchResult:
    """Fetch transcripts for each ticker/quarter pair, serving from cache where possible.

    Absent transcripts are recorded in .missing rather than raised - thin coverage is
    an expected condition for smaller names, not a failure.
    """
    quarters = quarters or recent_quarters(3)
    result = FetchResult()
    last_call = 0.0

    for ticker in tickers:
        for quarter in quarters:
            segments = _read_cache(ticker, quarter) if use_cache else None
            from_cache = segments is not None

            if not from_cache:
                if api_key is None:
                    api_key = config.require_alphavantage_key()
                elapsed = time.monotonic() - last_call
                if elapsed < MIN_SECONDS_BETWEEN_CALLS:
                    time.sleep(MIN_SECONDS_BETWEEN_CALLS - elapsed)
                segments = _call_api(ticker, quarter, api_key)
                last_call = time.monotonic()
                result.api_calls += 1
                _write_cache(ticker, quarter, segments)

            if segments:
                result.transcripts.append(
                    Transcript(ticker=ticker, quarter=quarter, segments=segments,
                               from_cache=from_cache)
                )
            else:
                result.missing.append((ticker, quarter))

    return result
