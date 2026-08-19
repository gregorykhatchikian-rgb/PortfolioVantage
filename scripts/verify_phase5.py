"""Phase 5 verification: dashboard comes up and serves real data.

Automated:
  - the data layer returns real records for at least two tickers, each traceable
    to an extraction file (not sample/placeholder data)
  - the Streamlit server starts and reports healthy
  - the app module imports and its startup path runs without raising

Left to you: whether the charts actually look right, and whether they update when
you switch holdings. That needs eyes on a browser.

Run:  python scripts/verify_phase5.py
"""

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.trend_aggregator import (  # noqa: E402
    EXTRACTION_DIR, build_series, consecutive_declines, load_extractions, theme_matrix,
)

failures: list[str] = []


def report(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    if not ok:
        failures.append(name)
    return ok


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def check_data_layer() -> None:
    points = load_extractions()
    series = build_series(points)

    report("data layer returns >=2 tickers", len(series) >= 2, f"{len(series)} tickers")

    # Placeholder data is the specific risk the plan calls out: sample records left
    # over from the design step rendering as though they were real analysis.
    traceable = all((EXTRACTION_DIR / p.source_file).exists() for p in points)
    report("every record traces to an extraction file", traceable)

    on_disk = set()
    for path in EXTRACTION_DIR.glob("*.json"):
        raw = json.loads(path.read_text())
        on_disk.add((raw["ticker"], raw["quarter"], float(raw["sentiment_score"])))
    rendered = {(p.ticker, p.quarter, p.sentiment_score) for p in points}
    report("rendered values match files exactly", rendered == on_disk,
           "" if rendered == on_disk else f"{len(rendered ^ on_disk)} differ")

    try:
        matrix = theme_matrix(points)
        report("theme matrix builds", not matrix.empty,
               f"{matrix.shape[0]} themes x {matrix.shape[1]} tickers")
    except Exception as exc:  # noqa: BLE001
        report("theme matrix builds", False, f"{type(exc).__name__}: {exc}")

    flagged = {t: consecutive_declines(ps) for t, ps in series.items()
               if consecutive_declines(ps) >= 2}
    print(f"  [INFO] watch-list flags (2+ consecutive declines): "
          f"{flagged if flagged else 'none'}")


def check_app_renders() -> None:
    """Run the app the way Streamlit does and catch in-page exceptions.

    A plain HTTP fetch cannot do this: Streamlit serves a shell and pushes content
    over a websocket, then renders tracebacks INTO the page. The server stays
    healthy and returns 200 while the dashboard is visibly broken - which is
    exactly what an earlier version of this script reported as PASS.
    """
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    at.run()

    report("app renders without in-page exceptions", not at.exception,
           "" if not at.exception else "; ".join(str(e.value)[:120] for e in at.exception))
    # Both st.line_chart and st.altair_chart surface as vega_lite_chart elements;
    # AppTest has no typed accessor for either, so match on the element type.
    charts = [e for e in at.main if getattr(e, "type", None) == "vega_lite_chart"]
    report("dashboard renders trend chart and heatmap", len(charts) >= 2,
           f"{len(charts)} chart(s)")
    report("holdings table rendered", len(at.dataframe) >= 1,
           f"{len(at.dataframe)} dataframes")

    # Switching holdings must actually change the chart, not just the label.
    if at.selectbox and not at.exception:
        first = at.selectbox[0].value
        other = next((o for o in at.selectbox[0].options if o != first), None)
        if other:
            at.selectbox[0].set_value(other).run()
            report("switching holdings re-renders without error", not at.exception,
                   "" if not at.exception else str(at.exception[0].value)[:120])


def check_server() -> None:
    port = free_port()
    proc = subprocess.Popen(
        [str(ROOT / "venv" / "bin" / "streamlit"), "run", str(ROOT / "app.py"),
         "--server.port", str(port), "--server.headless", "true",
         "--browser.gatherUsageStats", "false"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        healthy = False
        for _ in range(40):
            if proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/_stcore/health", timeout=2) as r:
                    if r.status == 200 and r.read().decode().strip() == "ok":
                        healthy = True
                        break
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
                time.sleep(0.5)
        report("streamlit server starts and reports healthy", healthy,
               f"port {port}" if healthy else "never became healthy")

        if healthy:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as r:
                body = r.read().decode(errors="replace")
            report("app root serves a page", r.status == 200 and len(body) > 500,
                   f"{len(body)} bytes")
    finally:
        proc.terminate()
        try:
            out = proc.communicate(timeout=10)[0] or ""
        except subprocess.TimeoutExpired:
            proc.kill()
            out = proc.communicate()[0] or ""

    bad = [ln for ln in out.splitlines()
           if "Traceback" in ln or "Error:" in ln or "Exception" in ln]
    report("no exceptions in server output", not bad,
           "" if not bad else "; ".join(bad[:3]))


def main() -> int:
    print("Phase 5 verification - dashboard\n")
    check_data_layer()
    print()
    check_app_renders()
    print()
    check_server()

    print()
    if failures:
        print(f"RESULT: FAIL - {len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("RESULT: PASS - all automated Phase 5 checks passed.\n")
    print("  VISUAL CHECK FOR YOU - not something code can confirm:")
    print("    Start it with:  ./venv/bin/streamlit run app.py")
    print("    Then check the trend line renders, and that it changes when you")
    print("    switch holdings in the dropdown.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
