"""Phase 3 verification: LLM extraction on a SINGLE transcript.

plan.md is explicit that this runs on one transcript before any batch processing,
because this phase has a check code cannot make. Split accordingly:

  automated  - does the response parse, are all fields present, is sentiment_score
               in range, is themes a non-empty list, do ticker/quarter match
  yours      - does a score of -0.35 "cautious" actually match how management
               sounded? Code can validate a number's shape, not its truth.

Offline checks run first so a parser regression is caught without spending quota.

Run:  python scripts/verify_phase3.py [--ticker AAPL] [--quarter 2026Q2]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402
from src.llm_extract import extract, strip_fences, validate  # noqa: E402
from src.transcript_fetcher import fetch_transcripts  # noqa: E402

failures: list[str] = []


def report(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    if not ok:
        failures.append(name)
    return ok


def offline_checks() -> None:
    """Parser and validator behaviour, no API calls."""
    print("Offline checks (no quota spent)")

    good = {"ticker": "AAPL", "quarter": "2026Q2", "sentiment_score": -0.35,
            "sentiment_label": "cautious", "themes": ["margin pressure"],
            "notable_shift": "Guidance language hedged.", "confidence": "medium"}

    report("valid object passes validation", validate(good, "AAPL", "2026Q2") == [])

    report("markdown fences stripped",
           strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}')
    report("prose around JSON stripped",
           strip_fences('Here you go:\n{"a": 1}\nHope that helps!') == '{"a": 1}')

    cases = [
        ("out-of-range score", {**good, "sentiment_score": 2.5}, "outside"),
        ("non-numeric score", {**good, "sentiment_score": "very bad"}, "not a number"),
        ("empty themes", {**good, "themes": []}, "empty"),
        ("themes as string", {**good, "themes": "margin pressure"}, "not a list"),
        ("bad confidence", {**good, "confidence": "pretty sure"}, "confidence not one of"),
        ("blank notable_shift", {**good, "notable_shift": "  "}, "notable_shift is blank"),
        ("wrong ticker echoed", {**good, "ticker": "MSFT"}, "ticker mismatch"),
        ("missing field", {k: v for k, v in good.items() if k != "themes"}, "missing field"),
    ]
    for name, obj, expect in cases:
        errs = validate(obj, "AAPL", "2026Q2")
        report(f"rejects {name}", any(expect in e for e in errs),
               "" if any(expect in e for e in errs) else f"errors were {errs}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="AAPL")
    parser.add_argument("--quarter", default="2026Q2")
    args = parser.parse_args()

    print("Phase 3 verification - LLM extraction (single transcript)\n")
    offline_checks()

    print(f"\nLive extraction: {args.ticker} {args.quarter}")
    fetched = fetch_transcripts([args.ticker], quarters=[args.quarter], api_key="cache-only")
    if not fetched.transcripts:
        print(f"  [FAIL] no cached transcript for {args.ticker} {args.quarter}")
        print("\nRESULT: FAIL - run verify_phase2.py first.")
        return 1

    transcript = fetched.transcripts[0]
    print(f"  input: {transcript.word_count:,} words, {len(transcript.segments)} segments")

    result = extract(transcript)
    report("extraction returned a usable object", result.ok,
           "" if result.ok else "; ".join(result.errors))
    report("succeeded within the retry budget", result.ok,
           f"{result.attempts} attempt(s)")
    if result.retry_reasons:
        print("        retries were needed - reasons:")
        for reason in result.retry_reasons:
            print(f"          {reason}")

    if not result.ok:
        print(f"\n  Raw model response:\n{result.raw_response[:800]}")
        print(f"\nRESULT: FAIL - {len(failures)} check(s) failed.")
        return 1

    print("\n  Extracted:")
    print("    " + json.dumps(result.data, indent=2).replace("\n", "\n    "))

    # Write the transcript out so the judgment call can actually be made.
    out = config.DATA_DIR / f"review_{args.ticker}_{args.quarter}.txt"
    out.write_text(transcript.raw_text)

    print()
    if failures:
        print(f"RESULT: FAIL - {len(failures)} check(s) failed: {', '.join(failures)}")
        return 1

    print("RESULT: PASS - all automated Phase 3 checks passed.\n")
    print("  JUDGMENT CALL FOR YOU - this is the one code cannot make:")
    print(f"    Does sentiment_score {result.data['sentiment_score']} "
          f"(\"{result.data['sentiment_label']}\") match how management actually sounded?")
    print(f"    Do these themes appear in the call? {result.data['themes']}")
    print(f"    Is this accurate? \"{result.data['notable_shift']}\"")
    print(f"\n    The full transcript is written to: {out.relative_to(config.PROJECT_ROOT)}")
    print("    Read the prepared remarks and the first few analyst answers, then say")
    print("    whether the read is fair before the other 23 get processed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
