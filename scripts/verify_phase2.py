"""Phase 2 verification: transcript fetching and caching.

Asserts (automated):
  - every portfolio ticker has at least one transcript with a non-zero word count
  - a repeat fetch is served entirely from cache, costing zero API calls
  - every ticker/quarter pair is either fetched or listed as missing

Escalates (judgment call, per plan.md Phase 2): whether a coverage gap is acceptable
to proceed with is the user's decision, not something code can settle.

Quota note: AlphaVantage's free tier allows ~25 requests/day, and one full run costs
tickers x quarters calls. Every successful call is cached the moment it lands, so a
run cut short by the daily limit resumes where it stopped rather than starting over.

Run:  python scripts/verify_phase2.py [--quarters N] [--tickers AAPL,NVDA]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402
from src.csv_loader import load_portfolio  # noqa: E402
from src.transcript_fetcher import (  # noqa: E402
    RateLimitedError,
    TranscriptAPIError,
    fetch_transcripts,
    recent_quarters,
)

failures: list[str] = []


def report(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    if not ok:
        failures.append(name)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quarters", type=int, default=3,
                        help="how many recent quarters per ticker (plan allows 2-4)")
    parser.add_argument("--tickers", type=str, default="",
                        help="comma-separated subset, for spending less quota")
    args = parser.parse_args()

    print("Phase 2 verification - transcript fetcher\n")

    portfolio = load_portfolio(config.DATA_DIR / "portfolio.csv")
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()] or \
        list(portfolio.holdings["ticker"])
    quarters = recent_quarters(args.quarters)

    print(f"  portfolio: {len(tickers)} tickers | quarters: {', '.join(quarters)}")
    print(f"  worst-case cost: {len(tickers) * len(quarters)} API calls "
          f"(cached pairs cost nothing)\n")

    try:
        result = fetch_transcripts(tickers, quarters=quarters)
    except RateLimitedError as exc:
        print(f"  [STOP] rate limited: {exc}")
        print("\n  Progress so far is cached. Rerun tomorrow to continue where this "
              "stopped - already-fetched quarters will not be refetched.")
        print("\nRESULT: FAIL - stopped on quota, not retrying in a loop.")
        return 1
    except config.MissingKeyError as exc:
        print(f"  [STOP] {exc}")
        print("\nRESULT: FAIL - cannot fetch without a valid API key.")
        return 1
    except TranscriptAPIError as exc:
        print(f"  [STOP] unexpected API response: {exc}")
        print("\nRESULT: FAIL")
        return 1

    print(f"  fetched: {len(result.transcripts)} transcripts "
          f"({result.api_calls} API calls, rest from cache)\n")

    # --- automated assertions -------------------------------------------------
    no_coverage = result.tickers_with_no_coverage(tickers)
    report("every ticker has >=1 non-empty transcript", not no_coverage,
           "" if not no_coverage else f"no coverage at all for: {', '.join(no_coverage)}")

    empties = [t for t in result.transcripts if t.word_count == 0]
    report("no fetched transcript is zero-length", not empties,
           "" if not empties else f"{len(empties)} empty: {[(t.ticker, t.quarter) for t in empties]}")

    accounted = len(result.transcripts) + len(result.missing)
    expected = len(tickers) * len(quarters)
    report("every ticker/quarter pair accounted for", accounted == expected,
           f"{expected} expected = {len(result.transcripts)} fetched + {len(result.missing)} missing")

    replay = fetch_transcripts(tickers, quarters=quarters)
    report("repeat run is fully cached", replay.api_calls == 0,
           f"{replay.api_calls} API calls on replay")

    # --- coverage detail ------------------------------------------------------
    print("\n  Coverage by ticker:")
    for ticker in tickers:
        got = result.for_ticker(ticker)
        found = ", ".join(f"{t.quarter}({t.word_count:,}w)" for t in got) or "none"
        print(f"    {ticker:6} {len(got)}/{len(quarters)}  {found}")

    if result.missing:
        print("\n  Not found (expected for thinly-covered names):")
        for ticker, quarter in result.missing:
            print(f"    - {ticker} {quarter}")

    print()
    if failures:
        print(f"RESULT: FAIL - {len(failures)} check(s) failed: {', '.join(failures)}")
        return 1

    print("RESULT: PASS - all automated Phase 2 checks passed.")
    if result.missing:
        print(
            "\n  JUDGMENT CALL FOR YOU: some quarters are missing (listed above). Code can "
            "confirm the gap exists but not whether it's acceptable - a mega-cap missing a "
            "quarter suggests a fetch problem, a thinly-covered name missing one is normal. "
            "Review the list before continuing to Phase 3."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
