"""Phase 1 verification: portfolio CSV ingestion.

Two cases are checked:

  A. data/portfolio.csv - the working sample portfolio. Must load with zero issues.
  B. tests/fixtures/portfolio_messy.csv - deliberately broken rows. Proves one bad
     row can't take down the pipeline, and that every rejection is reported.

Per plan.md, the assertions are row accounting (every source row kept, merged or
dropped - never silently vanished) and no null ticker/weight surviving cleaning.
Flagged rows are always listed; the full holdings table is only printed on failure.

Run:  python scripts/verify_phase1.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import PROJECT_ROOT  # noqa: E402
from src.csv_loader import PortfolioLoadResult, load_portfolio  # noqa: E402

failures: list[str] = []


def report(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    if not ok:
        failures.append(name)
    return ok


def check_accounting(result: PortfolioLoadResult) -> bool:
    ok = result.accounted_rows == result.source_rows
    return report(
        "every source row accounted for",
        ok,
        f"{result.source_rows} source = {len(result.holdings)} kept "
        f"+ {len(result.by_action('merged'))} merged + {len(result.by_action('dropped'))} dropped",
    )


def check_no_nulls(result: PortfolioLoadResult) -> bool:
    df = result.holdings
    if df.empty:
        return report("no null ticker/weight after cleaning", False, "no rows survived cleaning")
    nulls = {c: int(df[c].isna().sum()) for c in ("ticker", "shares", "weight")}
    ok = sum(nulls.values()) == 0
    return report("no null ticker/weight after cleaning", ok, "" if ok else f"nulls found: {nulls}")


def list_issues(result: PortfolioLoadResult) -> None:
    if not result.issues:
        print("  (no rows flagged)")
        return
    for issue in result.issues:
        print(f"    - {issue}")


def case_clean() -> None:
    print("Case A: data/portfolio.csv (working sample)")
    result = load_portfolio(PROJECT_ROOT / "data" / "portfolio.csv")

    check_accounting(result)
    check_no_nulls(result)
    report("loads with zero flagged rows", not result.issues, f"{len(result.issues)} flagged")

    weight_sum = result.weight_sum
    report(
        "weights sum to ~1.0",
        abs(weight_sum - 1.0) < 0.01,
        f"sum = {weight_sum:.4f} across {len(result.holdings)} holdings",
    )

    if failures:
        print("\n  Holdings table (shown because a check failed):")
        print(result.holdings.to_string(index=False))


def case_messy() -> None:
    print("\nCase B: tests/fixtures/portfolio_messy.csv (deliberately broken)")
    result = load_portfolio(PROJECT_ROOT / "tests" / "fixtures" / "portfolio_messy.csv")

    before = len(failures)

    check_accounting(result)
    check_no_nulls(result)

    # The fixture is fixed, so the exact outcome is known and worth pinning down -
    # "it didn't crash" would pass even if validation silently stopped working.
    expected_kept = {"AAPL", "NVDA", "JPM", "BRK.B", "PG"}
    actual_kept = set(result.holdings["ticker"])
    report(
        "exactly the valid tickers survive",
        actual_kept == expected_kept,
        ""
        if actual_kept == expected_kept
        else f"expected {sorted(expected_kept)}, got {sorted(actual_kept)}",
    )

    report("4 unusable rows dropped", len(result.by_action("dropped")) == 4,
           f"{len(result.by_action('dropped'))} dropped")
    report("1 duplicate row merged", len(result.by_action("merged")) == 1,
           f"{len(result.by_action('merged'))} merged")

    # Duplicate NVDA lots (30 + 20 shares, 0.22 + 0.08 weight) must combine, not overwrite.
    nvda = result.holdings.loc[result.holdings["ticker"] == "NVDA"]
    combined_ok = (
        not nvda.empty
        and float(nvda["shares"].iloc[0]) == 50.0
        and abs(float(nvda["weight"].iloc[0]) - 0.30) < 1e-9
    )
    report("duplicate lots combined, not overwritten", combined_ok,
           "" if combined_ok else f"NVDA row: {nvda.to_dict('records')}")

    print("\n  Flagged rows:")
    list_issues(result)

    if len(failures) > before:
        print("\n  Holdings table (shown because a check failed):")
        print(result.holdings.to_string(index=False))


def main() -> int:
    print("Phase 1 verification - portfolio CSV ingestion\n")
    try:
        case_clean()
        case_messy()
    except Exception as exc:  # noqa: BLE001 - report exactly what happened, don't mask it
        print(f"\nRESULT: FAIL - unexpected {type(exc).__name__}: {exc}")
        return 1

    print()
    if failures:
        print(f"RESULT: FAIL - {len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("RESULT: PASS - all Phase 1 checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
