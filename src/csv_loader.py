"""Phase 1: load and validate the portfolio CSV.

The guiding rule (plan.md, Phase 1) is that one bad row must never take down the
pipeline. So every source row ends up in exactly one of three states:

  kept     - usable, present in .holdings
  merged   - a duplicate ticker folded into an earlier row
  dropped  - unusable, with a stated reason

Nothing is discarded silently. `source_rows` always equals kept + merged + dropped,
which is the invariant verify_phase1.py asserts.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

# Covers US common stock and share-class tickers like BRK.B and RDS-A.
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9]{0,5}([.\-][A-Z])?$")

COLUMNS = ("ticker", "shares", "weight")


@dataclass(frozen=True)
class RowIssue:
    """One thing that was wrong with one source row, and what was done about it."""

    row: int  # 1-based data row number, matching the source file ignoring the header
    ticker: str
    problem: str
    action: str  # "repaired" | "merged" | "dropped"

    def __str__(self) -> str:
        label = self.ticker or "<blank>"
        return f"row {self.row} ({label}): {self.problem} -> {self.action}"


@dataclass
class PortfolioLoadResult:
    holdings: pd.DataFrame
    issues: list[RowIssue] = field(default_factory=list)
    source_rows: int = 0

    def by_action(self, action: str) -> list[RowIssue]:
        return [i for i in self.issues if i.action == action]

    @property
    def accounted_rows(self) -> int:
        """Every source row should be represented exactly once."""
        return len(self.holdings) + len(self.by_action("merged")) + len(self.by_action("dropped"))

    @property
    def weight_sum(self) -> float:
        return float(self.holdings["weight"].sum()) if len(self.holdings) else 0.0


class PortfolioFormatError(ValueError):
    """The file isn't a portfolio CSV at all - a hard failure, not a bad row."""


def _clean_ticker(raw: object) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    return str(raw).strip().upper()


def _to_number(raw: object) -> float | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    try:
        return float(str(raw).strip().replace(",", "").replace("%", ""))
    except ValueError:
        return None


def load_portfolio(path: str | Path) -> PortfolioLoadResult:
    """Read a portfolio CSV into validated holdings plus a list of what went wrong."""
    path = Path(path)
    if not path.exists():
        raise PortfolioFormatError(f"portfolio CSV not found: {path}")

    raw = pd.read_csv(path, dtype=str, keep_default_na=True, skip_blank_lines=True)
    raw.columns = [str(c).strip().lower() for c in raw.columns]

    missing = [c for c in COLUMNS if c not in raw.columns]
    if missing:
        raise PortfolioFormatError(
            f"portfolio CSV is missing required column(s): {', '.join(missing)}. "
            f"Expected header: {','.join(COLUMNS)}"
        )

    issues: list[RowIssue] = []
    kept: list[dict] = []
    seen: dict[str, int] = {}  # ticker -> index into kept

    for offset, record in enumerate(raw.to_dict("records"), start=1):
        original = str(record.get("ticker") or "").strip()
        ticker = _clean_ticker(record.get("ticker"))
        shares = _to_number(record.get("shares"))
        weight = _to_number(record.get("weight"))

        if not ticker:
            issues.append(RowIssue(offset, "", "ticker is blank", "dropped"))
            continue
        if not TICKER_RE.match(ticker):
            issues.append(RowIssue(offset, ticker, "ticker is not a valid symbol", "dropped"))
            continue
        if shares is None:
            issues.append(RowIssue(offset, ticker, "shares is missing or non-numeric", "dropped"))
            continue
        if shares <= 0:
            issues.append(RowIssue(offset, ticker, f"shares is not positive ({shares:g})", "dropped"))
            continue
        if weight is None:
            issues.append(RowIssue(offset, ticker, "weight is missing or non-numeric", "dropped"))
            continue
        if not 0 < weight <= 1:
            issues.append(
                RowIssue(offset, ticker, f"weight outside (0, 1] ({weight:g})", "dropped")
            )
            continue

        if original != ticker:
            issues.append(
                RowIssue(offset, ticker, f"ticker normalised from {original!r}", "repaired")
            )

        if ticker in seen:
            # Same holding listed twice - two lots of one position. Combining them is
            # the finance-correct reading, so merge rather than discard either row.
            prior = kept[seen[ticker]]
            prior["shares"] += shares
            prior["weight"] += weight
            issues.append(
                RowIssue(offset, ticker, "duplicate ticker, combined with earlier row", "merged")
            )
            continue

        seen[ticker] = len(kept)
        kept.append({"ticker": ticker, "shares": shares, "weight": weight})

    holdings = pd.DataFrame(kept, columns=list(COLUMNS))
    if len(holdings):
        holdings = holdings.astype({"ticker": "string", "shares": "float64", "weight": "float64"})

    return PortfolioLoadResult(holdings=holdings, issues=issues, source_rows=len(raw))
