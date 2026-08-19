# Portfolio Earnings Trend Analyzer — Methodology and Limitations

## What it does

Takes a portfolio CSV, pulls recent earnings call transcripts for each holding, uses
an LLM to extract themes and a sentiment score from each call, and charts how those
shift quarter over quarter. Roughly 190,000 words of management commentary across 24
calls reduce to eight comparable trend lines and a cross-portfolio theme heatmap.

## Pipeline

```
portfolio.csv → transcripts → LLM extraction → trend series → dashboard
                                                      ↓
                                          price correlation (stretch)
```

| Stage | Implementation |
|---|---|
| Ingestion | `src/csv_loader.py` — every row kept, merged, or dropped with a stated reason |
| Transcripts | `src/transcript_fetcher.py` — AlphaVantage, cached to disk |
| Extraction | `src/llm_extract.py` — Llama 3.1 70B via NVIDIA NIM, JSON-only output |
| Aggregation | `src/trend_aggregator.py` — fiscal→calendar normalisation, theme counts |
| Dashboard | `app.py` — Streamlit |
| Correlation | `src/price_correlation.py` — yfinance |

Sample: 8 holdings × 3 quarters = 24 earnings calls, 4,924–11,402 words each.

## Design decisions worth defending

**Scoring calibration.** The first rubric put 0.4–1.0 in a single band. Three of four
holdings then scored *exactly* 0.8 — a dashboard built on that would have drawn a flat
line across the portfolio and told the user nothing. Splitting the bands and requiring
management's self-reported headwinds to cost points widened the spread across holdings
from 0.20 to 0.40. Calibration was not a polish step; it was the difference between a
working tool and a decorative one.

**Fiscal vs calendar quarters.** The provider labels transcripts by each company's own
fiscal calendar. The label `2026Q2` means Mar 2026 for Apple, Jul 2025 for NVIDIA, and
Jun 2026 for JPMorgan — an 11-month span under one label. Everything downstream orders
by the calendar month each fiscal period actually ended. Sorting by the raw label would
have silently plotted points a year apart on the same tick.

**Label derived from score.** Initially the model returned both a score and a text
label, and they could disagree — 0.8 arriving as "confident" while 0.7 arrived "very
confident". The label is now computed from the score in code. The model's own label is
retained as `model_label`; it consistently describes lower than it scores.

**Rubric leakage.** With a free-text label the model began returning my own scoring-band
wording verbatim ("unambiguous strength") as its description of the call. The vocabulary
is now a closed set of six, enforced in validation.

**Verification over assertion.** Each phase has an automated check that prints PASS/FAIL.
Two failures are worth noting because both *passed* their checks while being wrong: the
model catalog endpoint answers without credentials, so it reported a valid key when the
key was invalid; and Streamlit renders tracebacks into the page while continuing to serve
healthy 200s, so a stderr check reported a working dashboard whose heatmap was crashing.
Both checks were rewritten. "Not rejected" is not "working."

## Findings

**1. Cross-portfolio themes are the strongest signal.** "AI adoption" appears in 4 of 8
holdings; at word level, 5 holdings mention adoption, 3 mention constraints, 3 mention
supply. A theme spreading across unrelated sectors is portfolio-level information that no
single call would reveal.

**2. Nothing in the portfolio is deteriorating on this measure.** No holding shows 2+
consecutive quarters of declining sentiment. XOM declined once (0.80 → 0.65) then held
flat. Reported as-is rather than loosening the threshold until something triggered.

**3. No detectable relationship between sentiment shifts and subsequent price.**
Pearson r = +0.30 over 13 observations, t = 1.04 against a 5% critical value of 2.201
(df=11). Direction agreed in 6 of 13 cases versus a 50% baseline.

That null result is weaker than it looks, and the reason matters more than the number:
**9 of the 13 observations had a sentiment change of exactly 0.00.** A near-constant
independent variable cannot correlate with anything. This measured the scoring resolution
more than it tested the hypothesis.

## Limitations

**Resolution, not randomness.** Scores land on only five distinct values (0.55, 0.65,
0.75, 0.80, 0.85) and nothing across 24 calls came out negative. Re-scoring is *not* the
problem: 9 repeat runs across 3 transcripts returned identical scores every time, so
movements reflect the transcripts rather than sampling noise. But a scale that never goes
below zero and snaps to five values is too coarse to detect quarter-over-quarter drift.

**Sample size.** 8 holdings, 3 quarters, one point in the market cycle. Nothing here
generalises.

**Survivorship and selection.** The holdings are large caps chosen for transcript
availability. Thinly-covered names — where this tool would be most useful, since nobody
is reading those calls — are exactly where transcript coverage fails.

**No call dates.** The provider returns fiscal period labels only, so the correlation
step approximates the call as period_end + 35 days. Several weeks of error at the entry
point is material for a 90-day return.

**Returns are unadjusted.** No benchmark subtraction. A stock that rose while the whole
index rose says more about the index than about the earnings call.

**Absolute scores are not validated against anything.** Themes were spot-checked against
transcript text and held up — claims about Apple's CEO transition and its dropping of
"net cash neutral" as a formal target were both verbatim-grounded, not hallucinated. But
no human has labelled a corpus to check whether 0.65 is *correct*.

## What I would do next

1. **Score comparatively, not absolutely.** Give the model the prior quarter's call and
   ask what changed. Models are markedly better at relative than absolute judgements, and
   this attacks the resolution problem at its root.
2. **Widen the sample** to 30+ holdings and 8 quarters, so the correlation step has
   enough variance to test anything.
3. **Benchmark-adjust returns** against a sector index.
4. **Hand-label 20 calls** to measure the model against human judgement.
