"""Batch Phase 3 extraction over every cached transcript, writing one JSON per call.

Results are written as they land, so an interrupted run resumes instead of
restarting, and reruns cost nothing. Failures are recorded and skipped rather
than aborting the batch - one unparseable call shouldn't cost the other 23.

Run:  python scripts/run_extraction.py [--force]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402
from src.csv_loader import load_portfolio  # noqa: E402
from src.llm_extract import extract  # noqa: E402
from src.transcript_fetcher import fetch_transcripts, recent_quarters  # noqa: E402

EXTRACTION_DIR = config.DATA_DIR / "extractions"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="re-extract even if cached")
    parser.add_argument("--quarters", type=int, default=3)
    args = parser.parse_args()

    EXTRACTION_DIR.mkdir(parents=True, exist_ok=True)
    portfolio = load_portfolio(config.DATA_DIR / "portfolio.csv")
    tickers = list(portfolio.holdings["ticker"])
    quarters = recent_quarters(args.quarters)

    fetched = fetch_transcripts(tickers, quarters=quarters, api_key="cache-only")
    print(f"{len(fetched.transcripts)} cached transcripts to process\n")

    done = skipped = failed = 0
    for t in fetched.transcripts:
        out = EXTRACTION_DIR / f"{t.ticker}_{t.quarter}.json"
        if out.exists() and not args.force:
            skipped += 1
            continue

        result = extract(t)
        if not result.ok:
            print(f"  FAIL  {t.ticker} {t.quarter}: {'; '.join(result.errors)[:110]}", flush=True)
            failed += 1
            continue

        payload = dict(result.data)
        payload["_source"] = {
            "word_count": t.word_count,
            "segments": len(t.segments),
            "attempts": result.attempts,
            "retry_reasons": result.retry_reasons,
        }
        out.write_text(json.dumps(payload, indent=2))
        done += 1
        print(f"  ok    {t.ticker:6} {t.quarter}  {payload['sentiment_score']:>5} "
              f"{payload['sentiment_label']:15} {', '.join(payload['themes'][:3])}", flush=True)

    print(f"\nextracted {done}, skipped {skipped} (already cached), failed {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
