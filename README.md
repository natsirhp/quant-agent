# Quant agent → Telegram

Claude does quantitative research and sends you a report on Telegram every day.

- **Market analysis**: returns, volatility, RSI, trend, z-scores, correlations
- **Strategy backtests**: the strategies in `config.yaml`, without look-ahead and with trading costs
- **Portfolio risk**: volatility, beta, VaR/CVaR, risk contribution
- **Research**: news and upcoming dates from web search, each with a link

## How it works (Claude Pro/Max subscription)

```
GitHub Actions (daily at 22:17 UTC)
   ├─ installs Python + pandas, numpy, scipy, statsmodels, matplotlib, yfinance
   ├─ Claude Code (on your subscription) follows prompts/daily-report.md:
   │     pulls prices, runs the analysis and backtests, searches news
   │     writes out/report.md, out/telegram.txt, out/chart.png
   └─ python quant_agent.py send out  →  Telegram (summary + chart + full report)
```

| File | What it is |
|---|---|
| `prompts/daily-report.md` | What Claude does every day. Edit to change the report |
| `config.yaml` | Watchlist, benchmark, portfolio weights, strategies |
| `.github/workflows/daily-report.yml` | The daily schedule |
| `quant_agent.py` | `send` delivers a report folder to Telegram |

## Setup

### 1. Telegram bot
1. In Telegram, message **@BotFather** → `/newbot` → copy the token.
2. Send your new bot any message, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `message.chat.id`.

### 2. Claude subscription token
On your own computer, with Claude Code installed (`npm install -g @anthropic-ai/claude-code`), run:

```bash
claude setup-token
```

Log in with your Pro/Max account. It prints a long-lived token that starts with `sk-ant-oat`.

Then install the Claude GitHub App on this repo: **https://github.com/apps/claude**.

### 3. GitHub secrets
In **Settings → Secrets and variables → Actions → Repository secrets**, add:

| Name | Value |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | the token from `claude setup-token` |
| `TELEGRAM_BOT_TOKEN` | from BotFather |
| `TELEGRAM_CHAT_ID` | from getUpdates |

### 4. Test
Open **Actions → Daily quant report → Run workflow**. The report reaches Telegram in about 5–15 minutes. Every run also saves its files as a downloadable **quant-report** artifact.

## Changing things
- **What it covers**: edit `config.yaml`.
- **How it analyzes**: edit `prompts/daily-report.md`.
- **When it runs**: edit the `cron` line in the workflow. It uses UTC.

## Notes
- Runs count against your subscription's usage limits. A daily report is one long Claude Code session.
- Prices come from Yahoo Finance via `yfinance`, with Stooq as a fallback. This is free data, so a ticker can occasionally be missing, and the report says so when it is.
- This is research output, not investment advice.

## Alternative: API credits (Managed Agents)
If you later get API credits, `agents/quant-analyst/` and `python quant_agent.py daily` / `ask` run the same analysis as a hosted Managed Agent instead. Set it up with `ant apply agents/quant-analyst/agent.md agents/quant-analyst/environment.yaml` and the `ANTHROPIC_API_KEY` secret.
