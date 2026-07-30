# Portfolio Earnings Trend Analyzer - Build Plan (Claude Code Context)

This file is the project spec for Claude Code. It covers ground rules, architecture, data flow, build phases, and known pitfalls to plan around from the start. Save it as `docs/plan.md` in the project folder before starting a session.

## 0. Ground rules for Claude Code (read this before writing any code)

- Treat section 5 (Build phases) as the spec, not a suggestion. Build in order: Phase 0, then 1, then 2, and so on. Do not jump ahead.
- Every phase in section 5 has a **Verify** step. Wherever the check can be confirmed programmatically (an assertion, a schema validation, a count matching, a non-empty response), write that check in code and have it print a clear PASS/FAIL. Run it yourself, don't just ask the user to eyeball raw output for something code can already confirm.
- Only escalate to the user for confirmation when the check is genuinely subjective, i.e. something code can't judge on its own: does the extracted sentiment actually match the tone of the transcript, does the dashboard look right visually, does a flagged theme make sense. Say explicitly why that particular check needs their eyes.
- Never mark a phase complete just because the code ran without throwing an error. "It ran" is not "it verified." The automated check (or the user's confirmation, for the subjective ones) must actually pass.
- Do not fabricate or paraphrase what a verification result would look like. If a command fails, hangs, or returns something unexpected, stop and report exactly what happened. Do not move forward "assuming it would have worked."
- After a verification passes, stop and wait for the user to explicitly say "continue" before starting the next phase. Do not chain phases together automatically, even if every check was automated and passed.
- Do not introduce new libraries, services, features, or architecture changes that aren't in this document without asking first and getting a clear yes.
- If the user requests something mid-build that isn't in this plan (a new feature, a different tool, a UI change outside what was already designed), do not just implement it. Say plainly that it's outside the current plan, and ask whether they want to formally add it as a new phase or note before proceeding. Then wait.
- If the user seems to be improvising or drifting from the plan, gently redirect back to the current phase rather than following the tangent.
- The UI is already designed and lives in the `ui/` folder (built separately in Claude.ai from a design brief, then exported). Wire the backend to that existing design rather than redesigning it.

## Safety checks (hard stops, non-negotiable)

These apply at every phase, not just the one they happen to be listed under.

- **Missing or invalid API key:** stop immediately and ask the user to provide it. Never fabricate a placeholder key or silently switch to mocked responses without explicitly telling the user that's what's happening.
- **Verification output shows an error, empty result, or something that doesn't match expectations:** stop and report it plainly. Don't retry silently more than once, and don't move to the next phase hoping it resolves itself.
- **API keys and `.env` files:** never print full key values back to the user in chat, never commit them, and confirm `.env` is in `.gitignore` before the first commit.
- **Rate limit errors (HTTP 429):** stop and back off, don't loop retries aggressively enough to burn through free-tier quota.
- **Anything that would send real money, place a trade, or touch a live brokerage account:** this project never does this. If a future request implies it, stop and flag it, that's outside scope entirely.

## 1. Goal

Build a tool that takes a portfolio CSV as input, pulls recent earnings call transcripts for each holding, uses an LLM to extract themes and sentiment, tracks how those shift quarter over quarter, and surfaces which holdings have improving vs. deteriorating call sentiment. Stretch goal: check whether sentiment shifts correlate with subsequent price action.

## 2. Architecture overview

```
portfolio.csv
     |
     v
[1. CSV Loader] -> validated list of (ticker, shares, weight)
     |
     v
[2. Transcript Fetcher] -> raw transcripts per ticker, last N quarters
     |
     v
[3. LLM Extraction] -> structured JSON per transcript (themes, sentiment score, key quotes)
     |
     v
[4. Trend Aggregator] -> per-ticker time series of sentiment + theme frequency
     |
     v
[5. Dashboard] -> visual output, sentiment trend per holding, theme heatmap
     |
     v
[6. (Stretch) Price Correlation] -> did sentiment shift predict anything?
```

## 3. Tech stack

- **Language:** Python 3.11+
- **Data handling:** pandas
- **AI inference:** NVIDIA NIM API via build.nvidia.com
  - OpenAI-compatible endpoint, base URL: `https://integrate.api.nvidia.com/v1`
  - Get a free API key by creating a developer account at build.nvidia.com (no credit card required)
  - Model choice: pick a strong instruction-following model from the current catalog (e.g. a Llama or Nemotron variant); check build.nvidia.com directly for the current model list since it changes
  - Free tier is rate-limited (roughly 40 requests/minute as of mid-2026), fine for this project's scale, but batch/throttle calls, don't fire them all at once
  - Because it's OpenAI-compatible, use the `openai` Python SDK and just point `base_url` and `api_key` at NVIDIA's endpoint
- **Transcript data:** a financial data API with an earnings call transcript endpoint (Financial Modeling Prep and AlphaVantage both have options). Confirm current free-tier call limits before committing, they change.
- **Price data (Phase 6):** yfinance, a free Python library that pulls historical price data from Yahoo Finance with no API key needed. It's unofficial (it scrapes Yahoo rather than using a supported API), so it occasionally breaks when Yahoo changes something on their end, see the pitfall on this below.
- **Dashboard:** Streamlit for speed. Good enough for a resume demo, and you can screen-record it or deploy it free on Streamlit Community Cloud.

## 4. Data schemas

**Input CSV** (`portfolio.csv`):
```
ticker,shares,weight
AAPL,50,0.15
NVDA,30,0.22
...
```

**Transcript object** (internal, after fetch):
```json
{
  "ticker": "AAPL",
  "quarter": "Q2 2026",
  "call_date": "2026-05-01",
  "raw_text": "..."
}
```

**LLM extraction output** (force this as the model's response schema, JSON only, no preamble):
```json
{
  "ticker": "AAPL",
  "quarter": "Q2 2026",
  "sentiment_score": -0.35,
  "sentiment_label": "cautious",
  "themes": ["margin pressure", "AI capex", "guidance cut"],
  "notable_shift": "Management tone on guidance was notably more hedged than prior quarter",
  "confidence": "medium"
}
```
Keep `sentiment_score` on a fixed numeric scale (e.g. -1 to 1) so it's chartable. Have the model justify the score briefly in `notable_shift` so you can sanity-check outputs by hand, don't trust the number blind.

## 5. Build phases

**Phase 0: Setup**
- Repo scaffold, `.env` for API keys (never commit these), requirements.txt
- Test NVIDIA API connectivity with a single hardcoded prompt before building anything else
- **Verify (automated):** Claude Code runs the test call, asserts the response is non-empty and contains no error field, and prints PASS/FAIL. Fully objective, no user judgment needed. Only surface the raw output if it fails.

**Phase 1: CSV ingestion**
- Load and validate portfolio CSV
- Handle bad tickers, missing weights, duplicate rows gracefully, don't crash the pipeline on one bad row
- **Verify (automated):** Claude Code asserts the parsed row count matches the source CSV row count, and that no ticker/weight field is null after cleaning. Print PASS/FAIL with any flagged rows listed. Only show the full table to the user if the assertion fails.

**Phase 2: Transcript fetcher**
- Pull last 2 to 4 quarters of transcripts per ticker
- Cache raw transcripts locally (JSON or SQLite) so you're not re-fetching on every run, free-tier API limits will bite otherwise
- Handle missing transcripts (small caps or thinly covered names may not have them)
- **Verify (automated, with one judgment call):** Claude Code checks every ticker has at least one transcript with non-zero word count, and prints PASS/FAIL plus an explicit "not found" list for anything missing. The count check is automatic; deciding whether it's acceptable to proceed with a gap (e.g. a thinly-covered small cap) is the one thing that needs the user's call, since that's a judgment about the data, not something code can decide.

**Phase 3: LLM extraction**
- One function: transcript in, structured JSON out
- Force JSON-only output in the prompt, strip markdown fences before parsing, wrap in try/except
- Run this on ONE transcript first and manually check the output quality before batch processing
- Add basic retry logic for rate-limit errors (HTTP 429)
- **Verify (automated schema check, then one judgment call):** Claude Code validates the JSON against the expected schema automatically (all fields present, `sentiment_score` in range, `themes` is a non-empty list), prints PASS/FAIL. That part needs no human. Whether the sentiment score and themes actually match what's in the transcript is inherently subjective, code can't judge accuracy against meaning, so the user reads the one test case against the real transcript before batch processing starts.

**Phase 4: Trend aggregator**
- Build a per-ticker time series: sentiment score by quarter
- Track theme frequency across the portfolio (which themes are appearing across multiple holdings, that's a cross-portfolio trend signal, not just single-stock noise)
- **Verify (automated):** Claude Code asserts quarters are in chronological order per ticker and that every score traces back to a real Phase 3 output (not a default/placeholder value), prints PASS/FAIL. No user step needed unless it fails.

**Phase 5: Dashboard**
- Per-holding sentiment trend line
- Portfolio-wide theme heatmap (which themes are rising across your holdings)
- Simple flag: "sentiment declining 2+ consecutive quarters" as a watch-list indicator
- **Verify (automated where possible, then one visual check):** Claude Code starts the local server, confirms it comes up without errors, and hits the data endpoint directly to assert it returns real records (not the placeholder/sample data left over from the UI design step) for at least two tickers, prints PASS/FAIL. Actually seeing charts render correctly and update when switching holdings is a visual check that has to happen in a browser, so that part goes to the user, everything up to that point Claude Code confirms on its own.

**Phase 6 (stretch): Price correlation check**
- Pull price data around each call date using yfinance (`pip install yfinance`, `yf.Ticker("AAPL").history(...)`, no API key needed)
- Check whether sentiment shifts preceded price moves, report this honestly even if the answer is "no meaningful correlation," that's a legitimate and defensible finding for a resume project, don't force a signal that isn't there
- **Verify (automated):** Claude Code asserts the correlation statistic is a real computed number (not NaN) and checks the sample size against a minimum threshold, prints PASS/FAIL with the actual numbers shown. If it fails, say so explicitly rather than presenting a stub as a finished result. Interpreting what the number means for the writeup is still the user's call, code can confirm the math ran, not what it means.

## 6. Pitfalls to plan around from the start

- **Rate limits will bite during batch runs.** Build throttling/backoff in from Phase 2 onward, don't bolt it on after hitting 429s.
- **Transcript availability is uneven.** Mega-caps have clean data going back years; smaller names may have gaps or none at all. Handle this as an expected case, not an error.
- **LLM sentiment scores need spot-checking.** Don't assume the model is accurate just because the JSON parses. Manually review a sample against the actual transcript before trusting the pipeline.
- **Ticker and quarter alignment is fiddly.** Fiscal quarters don't always match calendar quarters; normalize this early or your trend lines will be misleading.
- **Don't oversell the correlation step.** If price correlation turns out weak or nonexistent, that's fine and worth stating plainly. A false "predictive signal" claim is the kind of thing that falls apart under interview questioning.
- **yfinance is unofficial and occasionally breaks.** It scrapes Yahoo Finance rather than using a supported API, so Yahoo-side changes can break it without warning (this has happened before, e.g. a 2025 site redesign). Pin the version in requirements.txt, and if it stops returning data mid-build, that's a known failure mode, not a bug in your code. Stooq is a free fallback with no API key if it comes to that.

## 7. Definition of done for a resume-ready version

- Portfolio CSV in, working sentiment trend dashboard out, for a real (or realistic sample) portfolio
- At least one clear, honestly-reported finding (e.g. "this holding's sentiment declined two straight quarters while price held up," or "no meaningful correlation was found, here's why that's still useful to know")
- A short written summary of methodology and limitations, this is what actually gets discussed in interviews
