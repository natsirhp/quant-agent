# Quant agent → Telegram

A Claude Managed Agent that does quantitative research and sends you a report on Telegram every day.

- **Market analysis**: returns, volatility, RSI, trend, z-scores, correlations
- **Strategy backtests**: the strategies in `config.yaml`, without look-ahead and with trading costs
- **Portfolio risk**: volatility, beta, VaR/CVaR, risk contribution, optional optimization
- **Research**: news and upcoming dates from web search, each with a link

## How it works

```
GitHub Actions (daily cron)
   └─ quant_agent.py daily
        ├─ starts a session of the quant-analyst agent   (Anthropic runs the loop + a Python sandbox)
        │     agent pulls prices (yfinance), runs the analysis, searches news
        │     writes report.md, telegram.txt, chart.png to /mnt/session/outputs/
        │     a grader checks the report against a rubric; the agent revises once if needed
        ├─ downloads those files
        └─ sends them to Telegram (summary message + chart + full report)
```

The Telegram bot token stays with the runner and never reaches the agent's sandbox. Telegram puts the token in the URL path, and Anthropic's vault can only inject secrets into headers and request bodies.

| File | What it is |
|---|---|
| `agents/quant-analyst/agent.md` | Agent definition: model, tools, system prompt |
| `agents/quant-analyst/environment.yaml` | Sandbox: Python packages and networking |
| `config.yaml` | Watchlist, benchmark, portfolio weights, strategies, cost cap per run |
| `quant_agent.py` | Runner: `daily` (report → Telegram) and `ask` (one-off question) |
| `.github/workflows/daily-report.yml` | The daily schedule |

## Setup

### 1. Telegram bot
1. In Telegram, message **@BotFather** → `/newbot` → copy the token.
2. Send your new bot any message, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and copy `message.chat.id`.

### 2. Create the agent (once)
Install the `ant` CLI (`brew install anthropics/tap/ant`, or a release from github.com/anthropics/anthropic-cli), then log in with `ant auth login` or export `ANTHROPIC_API_KEY`. From this directory:

```bash
ant apply --dry-run -v agents/quant-analyst/agent.md agents/quant-analyst/environment.yaml
```

```bash
ant apply agents/quant-analyst/agent.md agents/quant-analyst/environment.yaml
```

This writes `claude-lock.json`, which holds the agent and environment IDs. **Commit it.** The runner reads the IDs from it, and without it the next `ant apply` creates duplicates.

### 3. Try it locally
```bash
pip install -r requirements.txt
```

```bash
python quant_agent.py ask "Backtest a 20/100 SMA crossover on QQQ since 2010 vs buy-and-hold"
```

```bash
export TELEGRAM_BOT_TOKEN=...  TELEGRAM_CHAT_ID=...
python quant_agent.py daily
```

Output files are also saved under `out/<date>/`. Each run prints a link to its trace in the Claude Console.

### 4. Turn on the daily schedule
Push this folder to a GitHub repo, including `claude-lock.json`. Then in **Settings → Secrets and variables → Actions**, add:
`ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

The workflow runs every day at 22:17 UTC, after the US close. To change the time, edit the cron line. To run it right away, open **Actions → Daily quant report → Run workflow**.

## Changing things
- **What it covers**: edit `config.yaml`. You don't need to re-apply anything.
- **How it thinks**: edit `agents/quant-analyst/agent.md`, then run `ant apply`. This creates a new agent version, and new runs use it.
- **Cost**: each run has a hard cap of `max_cost_usd` (default $5), enforced by the platform. For a cheaper run, use `effort: medium` in `agent.md`, a shorter watchlist, or fewer strategies.

## Notes
- Managed Agents is a beta feature. You pay for tokens plus session runtime, and session history is kept until you delete it.
- Tools run under the `auto` permission policy: the platform screens each call. Nobody watches a scheduled run, so the runner denies any call that would wait for a human.
- Prices come from Yahoo Finance via `yfinance`, with Stooq as a fallback. This is free data with no SLA, so a ticker can occasionally be missing, and the report says so when it is.
- This is research output, not investment advice.
