# UI Design Brief - Portfolio Earnings Trend Analyzer

Paste this whole file (or upload it) into a new Claude.ai chat to design the dashboard. This is a design-only step: no backend, no real data, just the interface and mock data so Claude Code has a concrete target to wire up later.

## Paste this prompt to start

> Build me a React dashboard artifact for a tool called a Portfolio Earnings Trend Analyzer. It's a finance tool that shows how sentiment from company earnings calls is trending for each stock in a portfolio. Use Tailwind for styling, single file, no backend, use realistic mock data matching the schema below. Style direction: dark mode, fintech/trading-desk feel, clean and data-dense but not cluttered, muted color palette with green/red used specifically and only for sentiment direction (not overused elsewhere). Once the layout is working, I'll iterate with you on details.

## What the dashboard needs to show

1. **Holdings table** - ticker, shares, portfolio weight, latest sentiment score, latest sentiment label, a small trend arrow or indicator (up/down/flat) since last quarter
2. **Sentiment trend chart** - line chart of sentiment score over the last 2-4 quarters, for a single selected holding. Include a way to switch which holding is shown (dropdown or clicking a row in the holdings table)
3. **Portfolio-wide theme heatmap** - which themes (e.g. "margin pressure," "AI capex," "guidance cut") are showing up across multiple holdings, and how often, so a theme spreading across the portfolio is visually obvious
4. **Watch-list flag** - a clearly visible callout or badge for any holding with sentiment declining 2+ consecutive quarters
5. **(Stretch, only if there's room) Price overlay** - a secondary line on the sentiment trend chart showing price movement over the same period, for the optional Phase 6 correlation check

## Mock data to use (match this shape exactly, Claude Code will wire real data into this same structure later)

```json
{
  "holdings": [
    {
      "ticker": "AAPL",
      "shares": 50,
      "weight": 0.15,
      "sentiment_history": [
        { "quarter": "Q3 2025", "sentiment_score": 0.42, "sentiment_label": "confident", "themes": ["strong services growth"] },
        { "quarter": "Q4 2025", "sentiment_score": 0.10, "sentiment_label": "neutral", "themes": ["margin pressure", "AI capex"] },
        { "quarter": "Q1 2026", "sentiment_score": -0.35, "sentiment_label": "cautious", "themes": ["margin pressure", "guidance cut"] }
      ]
    },
    {
      "ticker": "NVDA",
      "shares": 30,
      "weight": 0.22,
      "sentiment_history": [
        { "quarter": "Q3 2025", "sentiment_score": 0.55, "sentiment_label": "very confident", "themes": ["AI capex", "demand strength"] },
        { "quarter": "Q4 2025", "sentiment_score": 0.60, "sentiment_label": "very confident", "themes": ["AI capex", "supply constraints"] },
        { "quarter": "Q1 2026", "sentiment_score": 0.48, "sentiment_label": "confident", "themes": ["AI capex"] }
      ]
    }
  ]
}
```
Add 2-3 more mock holdings with varied trends (one clearly improving, one clearly declining, one flat/mixed) so the dashboard actually demonstrates the range of what it's supposed to show, rather than looking flat with only two data points.

## Style inspiration (for direction, not to copy)

Reference points worth looking at for the general feel: modern crypto/fintech dashboard UIs, dark backgrounds with high-contrast data, card-based layout for the holdings table, sentiment color-coded charts. Think Bloomberg-terminal-meets-modern-web-app rather than a generic admin template, this should look like a tool someone on a trading desk would actually want to use, not a bootstrap starter kit.

## When you're done iterating

1. Use the artifact's download/export option to get the code
2. Unzip it into a `ui/` subfolder inside your project folder
3. Return to `plan.md`, Step 7, to hand the project to Claude Code
