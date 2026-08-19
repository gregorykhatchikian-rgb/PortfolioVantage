# Portfolio Earnings Trend Analyzer

Reads the earnings calls for every stock in a portfolio and shows which holdings have
improving or deteriorating management sentiment, and which themes are spreading across
the portfolio.

Roughly 190,000 words of management commentary across 24 calls reduce to eight
comparable trend lines and a theme heatmap.

## Why

Earnings numbers are reported instantly; the *language* around them is not. Hedged
guidance, a newly-introduced caveat, confidence draining out of how demand is described —
these carry information, and nobody reads 5,000–11,000 words per call across a whole
portfolio every quarter.

## Quick start

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
cp .env.example .env          # then add your API keys
./venv/bin/python scripts/verify_phase0.py    # confirms LLM connectivity
./venv/bin/streamlit run app.py
```

Two free API keys are needed: [build.nvidia.com](https://build.nvidia.com) for
inference and [alphavantage.co](https://www.alphavantage.co/support/#api-key) for
transcripts. Neither requires a credit card.

Extraction results for the sample portfolio are committed, so the dashboard runs without
re-spending an hour of inference.

## How it works

```
portfolio.csv → transcripts → LLM extraction → trend series → dashboard
                                                      ↓
                                          price correlation (stretch)
```

Each stage has a verification script that prints PASS/FAIL:

```bash
./venv/bin/python scripts/verify_phase1.py   # CSV ingestion
./venv/bin/python scripts/verify_phase2.py   # transcript fetching + cache
./venv/bin/python scripts/verify_phase3.py   # LLM extraction
./venv/bin/python scripts/verify_phase4.py   # trend aggregation
./venv/bin/python scripts/verify_phase5.py   # dashboard
./venv/bin/python scripts/verify_phase6.py   # price correlation
```

## Findings

- **"AI adoption" appears in 4 of 8 holdings** — a theme spreading across unrelated
  sectors is portfolio-level information no single call reveals.
- **No holding is deteriorating** on the 2+ consecutive declining quarters measure.
- **No detectable link between sentiment shifts and subsequent price** (r = +0.30,
  n = 13, not significant). The reason matters more than the number: 9 of 13
  observations had zero sentiment change, so this measured scoring resolution rather
  than testing the hypothesis.

Full reasoning, design decisions and limitations: **[docs/METHODOLOGY.md](docs/METHODOLOGY.md)**

## Stack

Python 3.12 · pandas · Llama 3.1 70B via NVIDIA NIM · AlphaVantage · Streamlit · yfinance
