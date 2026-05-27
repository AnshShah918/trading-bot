import os
import json
import time
import google.generativeai as genai
from datetime import date
from src.memory.trade_repository import get_closed_trades

AI_COST_FILE = "data/ai_costs.json"
MAX_CALLS_PER_DAY = 50
MAX_RETRIES = 2
TIMEOUT_SECONDS = 10
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
            "date": "",
            "circuit_broken": False
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
    return costs["today_calls"]


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
            f"₹{round(t.pnl or 0, 0)} "
            f"in {hold_days}d — "
            f"{t.entry_reason or ''} — "
            f"exit: {t.exit_reason or ''}"
        )

    return "\n".join(lines)


def call_gemini(prompt):
    global _consecutive_failures, _circuit_broken

    if _circuit_broken:
        return None

    genai.configure(
        api_key=os.getenv("GEMINI_API_KEY")
    )

    model = genai.GenerativeModel(
        "gemini-1.5-flash"
    )

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = model.generate_content(
                prompt,
                request_options={
                    "timeout": TIMEOUT_SECONDS
                }
            )

            _consecutive_failures = 0
            return response.text

        except Exception as e:
            _consecutive_failures += 1
            print(
                f"Gemini attempt {attempt + 1} "
                f"failed: {e}"
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


def analyse_setups(setups):
    global _circuit_broken

    if not setups:
        return setups

    # GUARDRAIL — circuit broken
    if _circuit_broken:
        print("AI circuit broken. Skipping.")
        return setups

    # GUARDRAIL — daily call limit
    calls_today = get_call_count()

    if calls_today >= MAX_CALLS_PER_DAY:
        print(
            f"Daily AI limit reached "
            f"({MAX_CALLS_PER_DAY} calls). Skipping."
        )
        return setups

    trade_history = build_trade_history()

    setups_text = "\n".join([
        f"{s['symbol']}: score={s['score']} "
        f"rsi={s['rsi']} "
        f"momentum={s['momentum']} "
        f"volume={s['volume_ratio']}x "
        f"tier={s['tier']} "
        f"risk={s['risk_pct']}%"
        for s in setups
    ])

    prompt = f"""You are an expert Indian stock market analyst.

TRADE HISTORY (learn from these):
{trade_history}

TODAY'S SETUPS:
{setups_text}

Respond ONLY with a JSON array. No explanation. No markdown. Just raw JSON.

[
  {{
    "symbol": "SYMBOL",
    "confidence": 7.5,
    "action": "BUY",
    "reasoning": "One sentence max"
  }}
]

Rules:
- confidence 1-10
- action: BUY or SKIP
- Only include setups you recommend (action=BUY)
- Flag sector concentration (avoid 2 stocks same group)
- Learn from trade history"""

    raw = call_gemini(prompt)

    # GUARDRAIL — AI unavailable, return setups as-is
    if raw is None:
        return setups

    track_call()

    # GUARDRAIL — parse failure, return setups as-is
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

    rec_map = {
        r["symbol"]: r
        for r in recommendations
        if r.get("action") == "BUY"
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
        else:
            # AI skipped it — still include
            # but flagged so user knows
            setup["ai_confidence"] = None
            setup["ai_reasoning"] = None

        result.append(setup)

    result.sort(
        key=lambda x: (
            x.get("ai_confidence") or 0
        ),
        reverse=True
    )

    return result


def get_cost_summary():
    costs = load_costs()
    costs = reset_if_new_day(costs)
    return {
        "today_calls": costs.get("today_calls", 0),
        "month_calls": costs.get("month_calls", 0),
        "circuit_broken": _circuit_broken,
        "calls_remaining": max(
            0,
            MAX_CALLS_PER_DAY
            -
            costs.get("today_calls", 0)
        )
    }
