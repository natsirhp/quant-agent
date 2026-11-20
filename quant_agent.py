"""Run the quant-analyst Managed Agent and deliver its daily report to Telegram.

    python quant_agent.py daily              # full daily report -> Telegram
    python quant_agent.py daily --no-send    # same, but only save files locally
    python quant_agent.py ask "Backtest a 20/100 SMA crossover on QQQ since 2010"
    python quant_agent.py send out           # send an existing report folder (used by the workflow)

The agent and its environment are created once with `ant apply` (see README);
this script only starts sessions. IDs come from claude-lock.json, or from the
AGENT_ID / ENVIRONMENT_ID environment variables.

Secrets read from the environment: ANTHROPIC_API_KEY (or an `ant auth login`
profile), TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID. The Telegram token never goes
to the agent: Telegram puts it in the URL path, which Anthropic's vault cannot
inject, so this runner sends the message itself.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import anthropic
import requests
import yaml

ROOT = Path(__file__).resolve().parent
LOCK_AGENT = "./agents/quant-analyst/agent.md"
LOCK_ENV = "./agents/quant-analyst/environment.yaml"
OUT_DIR = ROOT / "out"
MA_BETA = "managed-agents-2026-04-01"
TELEGRAM_LIMIT = 4096

RUBRIC = """# Daily quant report rubric
- /mnt/session/outputs/report.md, telegram.txt and chart.png all exist
- Every watchlist ticker and the benchmark appear in the report table, or are listed as not covered with a reason
- Every price, return and risk number comes from code run in this session (no estimated or remembered values)
- Portfolio section reports volatility, beta, 1-day 95% VaR and CVaR for the given weights
- Each requested strategy has a backtest with CAGR, Sharpe, max drawdown, and a buy-and-hold comparison, with signals lagged one bar
- Every news item has its date, outlet and link, and falls inside the last 7 days
- telegram.txt is plain text, at most 3500 characters, and readable on its own
- No buy/sell/hold instructions or price targets; both files end with the not-investment-advice line
"""


# ---------------------------------------------------------------- setup ----

def load_config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def load_ids() -> tuple[str, str]:
    agent_id = os.environ.get("AGENT_ID")
    env_id = os.environ.get("ENVIRONMENT_ID")
    lock = ROOT / "claude-lock.json"
    if (not agent_id or not env_id) and lock.exists():
        res = json.loads(lock.read_text()).get("resources", {})
        agent_id = agent_id or res.get(LOCK_AGENT, {}).get("id")
        env_id = env_id or res.get(LOCK_ENV, {}).get("id")
    if not agent_id or not env_id:
        sys.exit("No agent/environment ID. Run `ant apply` first (see README) "
                 "or set AGENT_ID and ENVIRONMENT_ID.")
    return agent_id, env_id


def daily_task(cfg: dict) -> str:
    today = dt.datetime.now(dt.timezone.utc).strftime("%A %Y-%m-%d %H:%M UTC")
    weights = cfg.get("portfolio") or "equal-weight across the watchlist"
    strategies = "\n".join(f"- {s}" for s in cfg.get("strategies", []))
    return (
        f"Produce today's daily report. Current time: {today}.\n"
        f"Watchlist: {', '.join(cfg['watchlist'])}\n"
        f"Benchmark: {cfg['benchmark']}\n"
        f"Portfolio weights: {json.dumps(weights)}\n"
        f"Strategies to backtest:\n{strategies}\n"
        "Write report.md, telegram.txt and chart.png to /mnt/session/outputs/ "
        "as your instructions describe."
    )


# -------------------------------------------------------------- session ----

def run_session(client: anthropic.Anthropic, agent_id: str, env_id: str,
                kickoff: dict, max_cost_usd: float) -> tuple[str, str]:
    """Start a session, stream it to the terminal until it finishes.
    Returns (session_id, last agent text)."""
    session = client.beta.sessions.create(
        agent=agent_id,  # string form: always the agent's latest version
        environment_id=env_id,
        title=f"quant {dt.date.today().isoformat()}",
        budget={"type": "limit",
                "max_list_cost": {"currency": "USD", "amount": str(int(max_cost_usd * 100))}},
    )
    print(f"Session {session.id}\n"
          f"Trace: https://platform.claude.com/workspaces/default/sessions/{session.id}\n",
          flush=True)

    last_text: list[str] = []
    sent = False
    done = False
    while not done:
        with client.beta.sessions.events.stream(session_id=session.id) as stream:
            if not sent:  # stream-first, then send
                client.beta.sessions.events.send(session_id=session.id, events=[kickoff])
                sent = True
            for event in stream:
                t = event.type
                if t == "agent.message":
                    last_text = [b.text for b in event.content if b.type == "text"]
                    print("".join(last_text), flush=True)
                elif t in ("agent.tool_use", "agent.mcp_tool_use"):
                    if getattr(event, "evaluated_permission", None) == "ask":
                        # Nobody is watching a scheduled run: deny calls the
                        # server could not clear on its own.
                        client.beta.sessions.events.send(session_id=session.id, events=[{
                            "type": "user.tool_confirmation",
                            "tool_use_id": event.id,
                            "result": "deny",
                            "deny_message": "Unattended run: this call needs a human. "
                                            "Find another way or note it as not covered.",
                        }])
                    else:
                        print(f"  [{getattr(event, 'name', 'tool')}]", flush=True)
                elif t == "span.outcome_evaluation_end":
                    print(f"  [grader: {event.result}]", flush=True)
                elif t == "session.status_idle":
                    reason = event.stop_reason.type
                    if reason == "budget_reached":
                        print(f"  [stopped: ${max_cost_usd} budget reached]", flush=True)
                    if reason != "requires_action":
                        done = True
                        break
                elif t == "session.status_terminated":
                    done = True
                    break
        if not done:  # stream dropped: check where the session is, then reattach
            status = client.beta.sessions.retrieve(session.id).status
            if status in ("idle", "terminated"):
                done = True
            else:
                time.sleep(2)
    return session.id, "\n".join(last_text)


def download_outputs(client: anthropic.Anthropic, session_id: str) -> dict[str, Path]:
    dest = OUT_DIR / dt.date.today().isoformat()
    dest.mkdir(parents=True, exist_ok=True)
    saved: dict[str, Path] = {}
    for _ in range(5):  # outputs are indexed a few seconds after idle
        files = client.beta.files.list(scope_id=session_id, betas=[MA_BETA]).data
        if files:
            break
        time.sleep(3)
    for f in files:
        name = Path(f.filename).name
        path = dest / name
        client.beta.files.download(f.id).write_to_file(path)
        saved[name] = path
    print(f"Saved {sorted(saved)} to {dest}")
    return saved


# ------------------------------------------------------------- telegram ----

def telegram(method: str, **kwargs) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=60, **kwargs)
    if r.status_code != 200 or not r.json().get("ok"):
        # Don't echo the URL: it contains the token.
        raise RuntimeError(f"Telegram {method} failed: {r.status_code} {r.text[:300]}")


def send_to_telegram(text: str, files: dict[str, Path]) -> None:
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    for i in range(0, len(text), TELEGRAM_LIMIT):
        telegram("sendMessage", data={"chat_id": chat_id, "text": text[i:i + TELEGRAM_LIMIT],
                                      "disable_web_page_preview": "true"})
    for name, path in files.items():
        if name.endswith(".png"):
            with path.open("rb") as fh:
                telegram("sendPhoto", data={"chat_id": chat_id}, files={"photo": (name, fh)})
    if "report.md" in files:
        with files["report.md"].open("rb") as fh:
            telegram("sendDocument", data={"chat_id": chat_id, "caption": "Full report"},
                     files={"document": (f"quant-report-{dt.date.today()}.md", fh)})
    print("Sent to Telegram.")


# ------------------------------------------------------------------ cli ----

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("daily", help="run the daily report and send it to Telegram")
    d.add_argument("--no-send", action="store_true", help="skip Telegram")
    a = sub.add_parser("ask", help="ask the agent a one-off quant question")
    a.add_argument("question")
    a.add_argument("--send", action="store_true", help="also send the answer to Telegram")
    s = sub.add_parser("send", help="send an existing report folder (telegram.txt, *.png, report.md) to Telegram")
    s.add_argument("folder")
    args = p.parse_args()

    if args.cmd == "send":  # used by the subscription (Claude Code) workflow; no API key needed
        folder = Path(args.folder)
        files = {f.name: f for f in sorted(folder.glob("*")) if f.is_file()} if folder.is_dir() else {}
        if "telegram.txt" in files:
            summary = files["telegram.txt"].read_text()
        else:
            summary = (f"Daily quant report failed: no telegram.txt in {folder}/. "
                       "Check the GitHub Actions log for this run.")
        send_to_telegram(summary, files)
        return

    cfg = load_config()
    agent_id, env_id = load_ids()
    client = anthropic.Anthropic()

    if args.cmd == "daily":
        kickoff = {"type": "user.define_outcome", "description": daily_task(cfg),
                   "rubric": {"type": "text", "content": RUBRIC}, "max_iterations": 2}
    else:
        kickoff = {"type": "user.message", "content": [{"type": "text", "text": args.question}]}

    session_id, last_text = run_session(client, agent_id, env_id, kickoff,
                                        float(cfg.get("max_cost_usd", 5)))
    files = download_outputs(client, session_id)

    if args.cmd == "daily" and not args.no_send:
        summary = files["telegram.txt"].read_text() if "telegram.txt" in files else (
            "Daily quant report: the agent did not write telegram.txt.\n\n" + last_text
            + f"\n\nSession: {session_id}")
        send_to_telegram(summary, files)
    elif args.cmd == "ask" and args.send:
        send_to_telegram(last_text or "(no answer)", {k: v for k, v in files.items() if k.endswith(".png")})


if __name__ == "__main__":
    main()
