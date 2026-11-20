# Quant agent → Telegram

Every morning Claude reads your Investment_Tracker Google Sheet, checks the news that affects what you own, and sends you a report on Telegram.

- **Market analysis**: returns, volatility, RSI, trend, z-scores, correlations
- **Strategy backtests**: the strategies in `config.yaml`, without look-ahead and with trading costs
- **Portfolio risk**: volatility, beta, VaR/CVaR, risk contribution
- **Research**: news and upcoming dates from web search, each with a link

## How it works (Claude Pro/Max subscription)

```
GitHub Actions (daily at 05:47 WIB = 22:47 UTC)
   ├─ fetch_sheet.py: reads your Investment_Tracker Google Sheet (read-only robot account)
   ├─ Claude Code (on your subscription) follows prompts/daily-report.md:
   │     analyses your holdings, splits price vs FX moves, checks the sheet,
   │     searches news that affects what you own
   │     writes out/report.md, out/telegram.txt, out/chart.png
   └─ python quant_agent.py send out  →  Telegram (summary + chart + full report)
```

| File | What it is |
|---|---|
| `prompts/daily-report.md` | What Claude does every day. Edit to change the report |
| `fetch_sheet.py` | Reads the Google Sheet (Dashboard, Holdings, Transactions, Prices, Monthly) |
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

### 4. Google Sheet access (private robot account)
1. **https://console.cloud.google.com** → create a project (e.g. `portfolio-report`).
2. **APIs & Services → Library** → search **Google Drive API** → **Enable**.
3. **IAM & Admin → Service Accounts → Create service account** → name it `portfolio-reader` → **Done** (no roles needed).
4. Open it → **Keys → Add key → Create new key → JSON**. A `.json` file downloads.
5. Copy the service account's email (`portfolio-reader@<project>.iam.gserviceaccount.com`), open the Investment_Tracker sheet → **Share** → paste that email → **Viewer** → untick "Notify" → **Share**.
6. Add two more repository secrets:

| Name | Value |
|---|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | the whole content of the downloaded `.json` file |
| `GOOGLE_SHEET_ID` | the ID in the sheet URL: `docs.google.com/spreadsheets/d/<ID>/edit` |

Then delete the `.json` file from your computer.

### 5. Test
Open **Actions → Daily quant report → Run workflow**. The report reaches Telegram in about 5–15 minutes. Every run also saves its files as a downloadable **portfolio-report** artifact (kept 30 days).

## Changing things
- **What it covers**: your Investment_Tracker sheet. Add or change holdings there.
- **How it analyzes**: edit `prompts/daily-report.md`.
- **When it runs**: edit the `cron` line in the workflow. It uses UTC.

## Notes
- Runs count against your subscription's usage limits. A daily report is one long Claude Code session.
- Prices come from Yahoo Finance via `yfinance`, with Stooq as a fallback. This is free data, so a ticker can occasionally be missing, and the report says so when it is.
- This is research output, not investment advice.

## Alternative: API credits (Managed Agents)
If you later get API credits, `agents/quant-analyst/` and `python quant_agent.py daily` / `ask` run the same analysis as a hosted Managed Agent instead. Set it up with `ant apply agents/quant-analyst/agent.md agents/quant-analyst/environment.yaml` and the `ANTHROPIC_API_KEY` secret.
