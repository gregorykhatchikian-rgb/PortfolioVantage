"""Phase 6 verification: price correlation check.

Asserts (automated, per plan.md):
  - the correlation statistic is a real computed number, not NaN
  - the sample size meets a stated minimum

Interpreting what the number means is the user's job. This script reports the
actual figures either way; it does not present a stub as a finished result, and a
null finding is reported as a null finding.

Run:  python scripts/verify_phase6.py
"""

import math
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.price_correlation import (  # noqa: E402
    build_observations, load_prices, pearson, t_statistic,
)
from src.trend_aggregator import build_series, load_extractions  # noqa: E402

MIN_SAMPLE = 10
# Two-sided 5% critical t for df=n-2, for the sample sizes this project produces.
CRITICAL_T = {10: 2.306, 11: 2.262, 12: 2.228, 13: 2.201, 14: 2.179,
              15: 2.160, 16: 2.145, 17: 2.131, 18: 2.120}

failures: list[str] = []


def report(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    if not ok:
        failures.append(name)
    return ok


def main() -> int:
    print("Phase 6 verification - sentiment vs subsequent price move\n")

    series = build_series(load_extractions())
    all_points = [p for ps in series.values() for p in ps]
    tickers = sorted(series)
    start = min(p.period_end for p in all_points)
    end = max(p.period_end for p in all_points) + timedelta(days=200)

    print(f"  fetching prices: {len(tickers)} tickers, {start:%b %Y} to {end:%b %Y}")
    prices, err = load_prices(tickers, start, end)
    if prices is None:
        print(f"  [STOP] {err}")
        print("\n  This is a known failure mode, not a bug: yfinance scrapes Yahoo and")
        print("  breaks when Yahoo changes their site (plan.md section 6).")
        print("\nRESULT: FAIL - no price data, correlation not computed.")
        return 1

    obs = build_observations(series, prices)
    report(f"sample size >= {MIN_SAMPLE}", len(obs) >= MIN_SAMPLE, f"n = {len(obs)}")

    if not obs:
        print("\nRESULT: FAIL - no usable observations.")
        return 1

    xs = [o.delta_sentiment for o in obs]
    ys = [o.forward_return for o in obs]
    r = pearson(xs, ys)

    real_number = r is not None and not math.isnan(r)
    report("correlation is a real computed number", real_number,
           f"r = {r:.4f}" if real_number else
           "undefined - sentiment changes have zero variance in this sample")

    print("\n  Observations (sentiment change -> next ~90d price move):")
    for o in sorted(obs, key=lambda o: o.delta_sentiment):
        mark = "agree" if o.agreed else "disagree"
        print(f"    {o.ticker:6} {o.from_quarter}->{o.to_quarter}  "
              f"dS {o.delta_sentiment:+.2f}   return {o.forward_return:+7.2%}   {mark}")

    agreed = sum(1 for o in obs if o.agreed)
    moved = [o for o in obs if o.delta_sentiment != 0]
    print(f"\n  Direction agreed in {agreed}/{len(obs)} observations "
          f"({agreed / len(obs):.0%}); coin-flip baseline is 50%.")
    print(f"  Observations where sentiment actually changed: {len(moved)}/{len(obs)}")

    if real_number:
        n = len(obs)
        t = t_statistic(r, n)
        crit = CRITICAL_T.get(n)
        print(f"\n  Pearson r = {r:+.4f}  (n = {n}, t = {t:+.3f})")
        if crit:
            sig = abs(t) > crit
            print(f"  Two-sided 5% critical t for df={n - 2} is {crit}: "
                  f"{'exceeds threshold' if sig else 'does NOT exceed threshold'}")
            if not sig:
                print("  => No statistically detectable relationship in this sample.")
                print("     That is a legitimate result, not a failed experiment. Report it")
                print("     as-is rather than tuning windows until something appears.")

    print()
    if failures:
        print(f"RESULT: FAIL - {len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("RESULT: PASS - correlation computed on a real sample.")
    print("\n  YOUR CALL: what the number means for the writeup. Code confirms the")
    print("  maths ran on real data; it cannot tell you whether the finding is")
    print("  interesting or whether the sample is large enough to trust.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
