"""Phase 4 verification: per-ticker trend series and portfolio theme frequency.

Asserts (all automated, per plan.md - no user step unless something fails):
  - every portfolio ticker has a series
  - each series is in true chronological order (by real period end, not label)
  - every score traces to an extraction file on disk that actually contains it,
    so no point can be a default or placeholder that silently reached the chart
  - scores are not all identical, which would mean the pipeline is emitting a
    constant rather than reading the transcripts

Run:  python scripts/verify_phase4.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402
from src.csv_loader import load_portfolio  # noqa: E402
from src.trend_aggregator import (  # noqa: E402
    EXTRACTION_DIR, build_series, keyword_frequency, load_extractions,
    period_end, theme_frequency, uses_default_calendar,
)

failures: list[str] = []


def report(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    if not ok:
        failures.append(name)
    return ok


def main() -> int:
    print("Phase 4 verification - trend aggregation\n")

    portfolio = load_portfolio(config.DATA_DIR / "portfolio.csv")
    tickers = list(portfolio.holdings["ticker"])
    points = load_extractions()
    series = build_series(points)

    report("extractions found on disk", bool(points), f"{len(points)} points")
    if not points:
        print("\nRESULT: FAIL - run scripts/run_extraction.py first.")
        return 1

    missing = [t for t in tickers if t not in series]
    report("every portfolio ticker has a series", not missing,
           "" if not missing else f"missing: {', '.join(missing)}")

    # Chronological order by real period end, which is the whole point of Phase 4.
    unordered = [t for t, ps in series.items()
                 if [p.period_end for p in ps] != sorted(p.period_end for p in ps)]
    report("every series is in chronological order", not unordered,
           "" if not unordered else f"out of order: {unordered}")

    # Provenance: each point must be readable back out of the file it claims.
    orphans, mismatches = [], []
    for p in points:
        path = EXTRACTION_DIR / p.source_file
        if not path.exists():
            orphans.append(p.source_file)
            continue
        raw = json.loads(path.read_text())
        if float(raw.get("sentiment_score", -99)) != p.sentiment_score or \
           raw.get("ticker") != p.ticker:
            mismatches.append(p.source_file)
    report("every score traces to its extraction file", not orphans and not mismatches,
           "" if not (orphans or mismatches) else f"orphans={orphans} mismatched={mismatches}")

    # A constant would satisfy every check above while being worthless.
    scores = [p.sentiment_score for p in points]
    report("scores vary across the portfolio", len(set(scores)) > 1,
           f"{len(set(scores))} distinct values, range {min(scores):.2f} to {max(scores):.2f}")

    empty_themes = [p.source_file for p in points if not p.themes]
    report("every point has at least one theme", not empty_themes,
           "" if not empty_themes else f"{len(empty_themes)} without themes")

    assumed = [t for t in tickers if uses_default_calendar(t)]
    if assumed:
        print(f"  [NOTE] fiscal calendar assumed (not in lookup table): {', '.join(assumed)}")

    # --- output ---------------------------------------------------------------
    print("\n  Sentiment by holding (oldest to newest, true calendar order):")
    for t in tickers:
        ps = series.get(t, [])
        if not ps:
            continue
        path = "  ".join(f"{p.period_end:%b %y} {p.sentiment_score:+.2f}" for p in ps)
        delta = ps[-1].sentiment_score - ps[0].sentiment_score
        arrow = "up" if delta > 0.05 else "down" if delta < -0.05 else "flat"
        print(f"    {t:6} {path}   {arrow} ({delta:+.2f})")

    print("\n  Themes across multiple holdings (exact match):")
    shared = [row for row in theme_frequency(points) if row[2] > 1]
    if shared:
        for theme, total, n_tickers in shared[:8]:
            print(f"    {theme:34} {n_tickers} holdings, {total} mentions")
    else:
        print("    none - no two holdings phrased a theme identically")

    print("\n  Same signal at word level (how many holdings mention it):")
    for word, n in keyword_frequency(points)[:8]:
        if n > 1:
            print(f"    {word:34} {n} holdings")

    print()
    if failures:
        print(f"RESULT: FAIL - {len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("RESULT: PASS - all automated Phase 4 checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
