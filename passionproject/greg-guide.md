# Greg's Guide - Portfolio Earnings Trend Analyzer

This is your guide, Greg. It has the project summary, the setup steps, and video resources. Two other files go alongside this one:
- `ui-design-brief.md` - hand this to Claude.ai when you get to Step 6 below
- `build-plan.md` - hand this to Claude Code, it's the technical spec, you don't need to read it closely yourself, just save it where Step 5 says to

## What it is
A tool that reads earnings call transcripts for the stocks in your portfolio, uses AI to pull out themes and tone, and flags which holdings have improving or deteriorating sentiment over time.

You upload a CSV of your holdings. It pulls recent earnings call transcripts for those tickers, runs them through an AI model to extract themes (capex, margins, guidance language, etc.) and an overall tone score, then shows you a simple dashboard: which stocks are trending up in sentiment, which are trending down, and how that lines up with price movement.

## Why it's a strong resume project
- Combines structured data (your CSV) with unstructured data (call transcripts), which is a genuinely useful and non-trivial skill
- Uses AI as a real analytical tool, not just a chatbot wrapper
- Has a finance-native use case: interviewers immediately get why it's useful
- Scoped small enough to actually finish in a few weeks

## How it works (plain language)
1. **Upload:** you drop in a CSV with your tickers and position sizes
2. **Pull:** the tool fetches the latest 2 to 4 earnings call transcripts for each ticker
3. **Extract:** an AI model reads each transcript and pulls out themes and a sentiment score
4. **Compare:** the tool tracks how sentiment and themes shift quarter over quarter
5. **Show:** a dashboard highlights which holdings are trending positive or negative, and whether that lines up with what the stock actually did

## Tech stack (plain terms)
- **Python** for the data pipeline
- **NVIDIA's free AI API** (build.nvidia.com) for the sentiment/theme extraction, no cost, no credit card
- **A transcript data source** (free-tier financial data API)
- **yfinance** for price data in the optional correlation step, free, no API key
- **A simple dashboard** (Streamlit is the fastest path, upgradeable to a proper web app later)

## Rough timeline
- Week 1: CSV upload + pull transcripts for a handful of tickers
- Week 2: AI extraction working end to end on one ticker
- Week 3: scale to full portfolio, build the trend view
- Week 4: polish dashboard, write up findings, backtest whether the signal means anything

## Before starting, get these
- Free NVIDIA developer account and API key (build.nvidia.com)
- Free-tier account with a financial data API for transcripts (e.g. Financial Modeling Prep or AlphaVantage, confirm current free-tier limits when signing up)
- A sample portfolio CSV to test with (ticker, shares, weight is enough)

---

# Manual Setup Guide (Do This First, In Order)

Do not skip ahead. Each step assumes the previous one is done. This whole section happens before you ever open Claude Code.

## Step 1: Update Claude and confirm your plan
1. If you already have the Claude app or Claude Code installed from before, update it first: open the Claude desktop app and let it auto-update, or if Claude Code is already installed run `claude update` in Terminal
2. Confirm you're on a Claude Pro or Max subscription, that's required to log into Claude Code later in this guide. Check at claude.ai under your account settings.
3. If you're on the free plan, upgrade now so you're not blocked at Step 5

## Step 2: Get your free NVIDIA AI API key
1. Go to build.nvidia.com in your browser
2. Create a free NVIDIA Developer account (no credit card needed)
3. Once logged in, open any model page (e.g. a Llama or Nemotron model)
4. Find the "Get API Key" button and generate a key
5. Paste that key into a notes doc for now, you'll need it later. Never post it publicly or commit it to GitHub.

## Step 3: Get a free transcript data API key
1. Go to Financial Modeling Prep (site.financialmodelingprep.com) or AlphaVantage (alphavantage.co) and sign up free
2. On their site, check the current free-tier limits (how many calls per day/month), these change over time, so confirm at signup rather than assuming
3. Save that API key in the same notes doc

## Step 4: Confirm Python and Claude Code are ready
You already have both installed, so this is just a quick check, not a fresh install.
1. Open Terminal and run `python3 --version`, confirm it shows 3.11 or newer (if it's older, update from python.org/downloads)
2. Run `claude --version`, confirm it runs. If it's out of date, run `claude update` (this doubles as a final check on top of Step 1)

## Step 5: Create the project folder
1. Create a new folder on your computer, e.g. `earnings-trend-analyzer`
2. Inside it, create a subfolder called `docs`
3. Save `build-plan.md` into `docs/plan.md`
4. Keep `ui-design-brief.md` and this guide handy but outside the `docs/` folder, they don't need to go to Claude Code

## Step 6: Design the UI first in Claude.ai, before touching Claude Code
Doing the visual design first gives Claude Code a concrete target to build toward instead of guessing at layout while also wiring up the backend. Keep these two jobs separate.
1. Go to claude.ai in your browser and start a new chat
2. Paste in the contents of `ui-design-brief.md` (or upload the file directly)
3. Ask for it as a React artifact styled with Tailwind, if it doesn't offer that by default
4. Keep iterating in that same chat, colors, layout, labels, until it actually looks right to you
5. When you're happy with it, use the artifact's download option to export the code
6. Unzip the download and place the contents into a `ui/` subfolder inside your project folder

## Step 7: Hand it to Claude Code
1. In Terminal, run `cd path/to/earnings-trend-analyzer`
2. Run `claude` to start a session inside the project folder
3. Your very first message in that session should be this, copy it exactly:

> Read docs/plan.md in full before doing anything else. Follow the build phases in section 5 in order, one at a time. For each phase, run the automated Verify check described for that phase and show me the actual PASS/FAIL output, don't just tell me it's done. Only ask me to manually confirm something when the plan says it's a judgment call code can't make on its own. Do not skip ahead, do not add features, libraries, or steps that aren't written in the plan. After each phase's verification passes, stop and wait for me to say "continue" before starting the next phase. If I ask for something mid-build that isn't in the plan, don't just do it, tell me it's outside the current plan and ask whether I want to formally add it before you proceed.

This forces Claude Code to treat the plan as the spec, verify its own work objectively where possible, and stops both of you from wandering off into scope creep mid-build.

---

# Learn More (Optional, But Useful Before or During the Build)

Videos, not required reading. Watch the financial ones before Phase 3, and the technical ones right before the phase they apply to, they'll make a lot more sense with the plan already in front of you.

## Financial concepts

- **What earnings calls actually contain and why they matter:** [How to Listen to a Stock's Earnings Call](https://www.youtube.com/watch?v=wzvbUalt4h8)
- **Reading tone and hedge language in management commentary (directly relevant to the sentiment extraction step):** [Earnings Call Decoded: Whispers, Revenue Trends, Cash Flow and Guidance](https://www.youtube.com/watch?v=QwB9hAe-bEI)
- **Why "sentiment declined and price didn't move" isn't necessarily a signal, core concept behind Phase 6:** [Correlation vs Causation Explained: Why Patterns Can Mislead Us](https://www.youtube.com/watch?v=ofweqU0Lz4I)

## Technical concepts

- **Forcing an LLM to return clean, structured JSON (this is Phase 3, the core of the project):** [A Guide to JSON output with LLM prompts](https://www.youtube.com/watch?v=a9Lhm2-TgQ8)
- **Using NVIDIA's free API specifically:** [Free NVIDIA AI API Tutorial](https://www.youtube.com/watch?v=Pe1E2-Vk1Ao)
- **Building the dashboard (Phase 5):** [Build a Streamlit Dashboard app in Python](https://www.youtube.com/watch?v=p2pXpcXPoGk)

## Using Claude to design the UI (Step 6 above)

- **How this workflow actually works, chat to working React app:** [I Built a React App in Minutes with Claude Design](https://www.youtube.com/watch?v=tvAAC6SU9KE)
- **Broader intro to Artifacts, if the above moves too fast:** [Learn About Artifacts in Claude AI: The Ultimate 2026 Guide](https://www.youtube.com/watch?v=MCQzb2iVrXE)
