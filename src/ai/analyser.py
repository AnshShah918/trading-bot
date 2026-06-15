import os
import json
import time
from google import genai
from datetime import date
from src.memory.trade_repository import (
    get_closed_trades,
    get_open_trades
)
from src.config.settings import (
    MAX_AI_CALLS_PER_DAY,
    MAX_RISK_PER_TRADE_PERCENT
)

AI_COST_FILE = "data/ai_costs.json"
MAX_CALLS_PER_DAY = MAX_AI_CALLS_PER_DAY
MAX_RETRIES = 2
TIMEOUT_SECONDS = 15
MAX_FAILURES_BEFORE_CIRCUIT_BREAK = 3

_consecutive_failures = 0
_circuit_broken = False


def load_costs():
    try:
        with open(AI_COST_FILE) as f:
            return json.load(f)
    except Exception:
        return {
            "today_calls": 0,
            "month_calls": 0,
            "date": ""
        }


def save_costs(costs):
    os.makedirs("data", exist_ok=True)
    with open(AI_COST_FILE, "w") as f:
        json.dump(costs, f)


def reset_if_new_day(costs):
    today = date.today().isoformat()
    if costs.get("date") != today:
        costs["today_calls"] = 0
        costs["date"] = today
    return costs


def track_call():
    costs = load_costs()
    costs = reset_if_new_day(costs)
    costs["today_calls"] += 1
    costs["month_calls"] += 1
    save_costs(costs)


def get_call_count():
    costs = load_costs()
    costs = reset_if_new_day(costs)
    return costs.get("today_calls", 0)


def build_trade_history():
    trades = get_closed_trades()

    if not trades:
        return "No trade history yet."

    lines = []

    for t in trades[-20:]:
        setup_bits = []
        if t.entry_snapshot:
            try:
                snapshot = json.loads(t.entry_snapshot)
                for key in (
                    "score",
                    "risk_adj_score",
                    "ai_confidence",
                    "rsi",
                    "momentum",
                    "volume_ratio",
                    "risk_pct",
                    "garch_vol"
                ):
                    if snapshot.get(key) is not None:
                        setup_bits.append(
                            f"{key}={snapshot[key]}"
                        )
            except Exception:
                setup_bits = []

        hold_days = (
            (t.exit_time - t.entry_time).days
            if t.exit_time and t.entry_time
            else 0
        )
        outcome = (
            "WIN" if t.pnl and t.pnl > 0
            else "LOSS"
        )
        lines.append(
            f"{t.symbol}: {outcome} "
            f"₹{round(t.net_pnl if t.net_pnl is not None else t.pnl or 0, 0)} "
            f"in {hold_days}d — "
            f"{t.entry_reason or ''} — "
            f"{', '.join(setup_bits)} — "
            f"exit: {t.exit_reason or ''}"
        )

    return "\n".join(lines)


def build_open_positions():
    trades = get_open_trades()

    if not trades:
        return "None"

    lines = []

    for t in trades:
        hold_days = (
            (
                __import__("datetime")
                .datetime.utcnow() - t.entry_time
            ).days
            if t.entry_time else 0
        )
        unrealised = (
            (
                (t.last_known_price or t.entry_price)
                - t.entry_price
            ) * t.quantity
        )
        lines.append(
            f"{t.symbol}: entry ₹{t.entry_price} "
            f"× {t.quantity} shares, "
            f"held {hold_days}d, "
            f"unrealised ₹{round(unrealised, 0)}"
        )

    return "\n".join(lines)


def call_gemini(prompt):
    global _consecutive_failures
    global _circuit_broken

    if _circuit_broken:
        return None

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        print("GEMINI_API_KEY not set. Skipping AI.")
        return None

    for attempt in range(MAX_RETRIES + 1):

        try:

            client = genai.Client(api_key=api_key)

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )

            _consecutive_failures = 0

            return response.text

        except Exception as e:

            _consecutive_failures += 1

            print(
                f"Gemini attempt "
                f"{attempt + 1} failed: {e}"
            )

            if (
                _consecutive_failures
                >=
                MAX_FAILURES_BEFORE_CIRCUIT_BREAK
            ):
                _circuit_broken = True
                print(
                    "Circuit breaker triggered. "
                    "AI disabled for this session."
                )
                return None

            if attempt < MAX_RETRIES:
                time.sleep(2)

    return None


def analyse_setups(
    setups,
    available_capital,
    max_picks=2
):
    global _circuit_broken

    if not setups:
        return setups

    if _circuit_broken:
        print("AI circuit broken. Passing through.")
        return setups

    if get_call_count() >= MAX_CALLS_PER_DAY:
        print("Daily AI limit reached. Passing through.")
        return setups

    trade_history = build_trade_history()
    open_positions = build_open_positions()

    # Open symbols — AI must not suggest these
    open_symbols = [
        t.symbol for t in get_open_trades()
    ]

    setups_text = "\n".join([
        f"{i+1}. {s['symbol']}: "
        f"score={s['score']} "
        f"risk_adj_score={s.get('risk_adj_score', s['score'])} "
        f"garch_vol={s.get('garch_vol', 'N/A')}% "
        f"rsi={s['rsi']} "
        f"momentum={s['momentum']} "
        f"volume={s['volume_ratio']}x "
        f"risk={s['risk_pct']}% "
        f"stop=₹{s['suggested_stop']} "
        f"target=₹{s['target_price']} "
        f"price=₹{s['current_price']}"
        for i, s in enumerate(setups)
    ])

    prompt = f"""You are a strict Indian stock market analyst managing a ₹50,000 portfolio.

AVAILABLE CAPITAL TO DEPLOY: ₹{available_capital:,.0f}
(This is after keeping reserve. Do NOT exceed this.)

CURRENTLY OPEN POSITIONS (DO NOT suggest these again):
{open_positions}

SYMBOLS ALREADY OPEN (NEVER suggest): {', '.join(open_symbols) if open_symbols else 'None'}

TODAY'S TOP SETUPS (scanner approved):
{setups_text}

TRADE HISTORY (learn from wins and losses):
{trade_history}

YOUR JOB:
- Pick MAXIMUM {max_picks} trades from the setups above
- If nothing is good enough, pick ZERO — that is fine
- Never suggest a symbol already in open positions
- Avoid 2 stocks from same business group (Adani/Tata/HDFC etc)
- Allocate specific ₹ amount per trade (must total <= ₹{available_capital:,.0f})
- Learn from trade history — avoid patterns that lost before
- Be strict — only high conviction trades

Respond ONLY with raw JSON array. No markdown. No explanation.

[
  {{
    "symbol": "SYMBOL",
    "confidence": 8.2,
    "action": "BUY",
    "allocation_inr": 12000,
    "reasoning": "One sentence max"
  }}
]

If no good trades: return empty array []"""

    raw = call_gemini(prompt)

    if raw is None:
        return setups

    track_call()

    try:
        cleaned = raw.strip()

        if "```" in cleaned:
            cleaned = (
                cleaned
                .split("```")[1]
                .replace("json", "")
                .strip()
            )

        recommendations = json.loads(cleaned)

    except Exception as e:
        print(f"AI parse error: {e}")
        return setups

    # Build map of AI picks
    rec_map = {
        r["symbol"]: r
        for r in recommendations
        if r.get("action") == "BUY"
        and r.get("symbol") not in open_symbols
    }

    result = []

    for setup in setups:
        rec = rec_map.get(setup["symbol"])

        if rec:
            setup["ai_confidence"] = (
                rec.get("confidence")
            )
            setup["ai_reasoning"] = (
                rec.get("reasoning", "")
            )
            setup["ai_allocation"] = (
                rec.get("allocation_inr", 0)
            )

            # Recalculate shares based on AI allocation
            if (
                rec.get("allocation_inr")
                and setup["current_price"] > 0
            ):
                allocation_shares = int(
                    rec["allocation_inr"]
                    /
                    setup["current_price"]
                )
                risk_budget = (
                    available_capital
                    * MAX_RISK_PER_TRADE_PERCENT
                )
                risk_per_share = setup.get(
                    "risk_per_share", 0
                )
                risk_shares = (
                    int(risk_budget / risk_per_share)
                    if risk_per_share > 0
                    else 0
                )
                setup["shares_to_buy"] = min(
                    allocation_shares,
                    risk_shares
                )
                setup["trade_value"] = round(
                    setup["shares_to_buy"]
                    *
                    setup["current_price"],
                    2
                )

            result.append(setup)

        # Stocks AI skipped are NOT sent to Telegram

    result.sort(
        key=lambda x: x.get("ai_confidence") or 0,
        reverse=True
    )

    return result


def get_cost_summary():
    costs = load_costs()
    costs = reset_if_new_day(costs)
    today_calls = costs.get("today_calls", 0)

    return {
        "today_calls": today_calls,
        "month_calls": costs.get("month_calls", 0),
        "circuit_broken": _circuit_broken,
        "calls_remaining": max(
            0, MAX_CALLS_PER_DAY - today_calls
        )
    }
