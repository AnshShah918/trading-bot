import os
import json
import anthropic
from src.memory.trade_repository import get_closed_trades

AI_COST_FILE = "data/ai_costs.json"


def load_costs():
    try:
        with open(AI_COST_FILE) as f:
            return json.load(f)
    except Exception:
        return {"today": 0.0, "month": 0.0, "date": ""}


def save_costs(costs):
    os.makedirs("data", exist_ok=True)
    with open(AI_COST_FILE, "w") as f:
        json.dump(costs, f)


def track_cost(input_tokens, output_tokens):
    # Sonnet pricing
    cost = (
        (input_tokens / 1_000_000) * 3.0
        +
        (output_tokens / 1_000_000) * 15.0
    )

    costs = load_costs()
    today = __import__("datetime").date.today().isoformat()

    if costs.get("date") != today:
        costs["today"] = 0.0
        costs["date"] = today

    costs["today"] = round(costs["today"] + cost, 4)
    costs["month"] = round(costs["month"] + cost, 4)
    save_costs(costs)

    return cost


def build_trade_history():
    trades = get_closed_trades()

    if not trades:
        return "No trade history yet."

    lines = []

    for t in trades[-20:]:  # last 20 trades
        hold_days = (
            (t.exit_time - t.entry_time).days
            if t.exit_time and t.entry_time else 0
        )
        outcome = "WIN" if t.pnl and t.pnl > 0 else "LOSS"
        lines.append(
            f"{t.symbol}: {outcome} ₹{round(t.pnl or 0, 0)} "
            f"in {hold_days}d — {t.entry_reason or ''} — exit: {t.exit_reason or ''}"
        )

    return "\n".join(lines)


def analyse_setups(setups):
    if not setups:
        return []

    client = anthropic.Anthropic(
        api_key=os.getenv("ANTHROPIC_API_KEY")
    )

    trade_history = build_trade_history()

    setups_text = "\n".join([
        f"{s['symbol']}: score={s['score']} rsi={s['rsi']} "
        f"momentum={s['momentum']} volume={s['volume_ratio']}x "
        f"tier={s['tier']} risk={s['risk_pct']}%"
        for s in setups
    ])

    prompt = f"""You are an expert Indian stock market analyst.

TRADE HISTORY (learn from these):
{trade_history}

TODAY'S SETUPS TO ANALYSE:
{setups_text}

For each setup, respond in this exact JSON format:
[
  {{
    "symbol": "SYMBOL",
    "confidence": 7.5,
    "action": "BUY",
    "reasoning": "One sentence explanation"
  }}
]

Rules:
- confidence 1-10 (only suggest setups >= 6.5)
- action: BUY or SKIP
- reasoning: one sentence, practical, specific
- Consider sector concentration (flag if multiple same group)
- Learn from trade history patterns
- Respond ONLY with the JSON array, no other text"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    track_cost(
        response.usage.input_tokens,
        response.usage.output_tokens
    )

    raw = response.content[0].text.strip()

    try:
        recommendations = json.loads(raw)
    except Exception:
        return []

    # Merge AI recommendations back into setups
    rec_map = {
        r["symbol"]: r
        for r in recommendations
    }

    result = []

    for setup in setups:
        rec = rec_map.get(setup["symbol"])
        if rec and rec["action"] == "BUY":
            setup["ai_confidence"] = rec["confidence"]
            setup["ai_reasoning"] = rec["reasoning"]
            result.append(setup)

    result.sort(
        key=lambda x: x.get("ai_confidence", 0),
        reverse=True
    )

    return result


def get_cost_summary():
    costs = load_costs()
    inr_rate = 84
    return {
        "today_usd": costs.get("today", 0),
        "today_inr": round(costs.get("today", 0) * inr_rate, 2),
        "month_usd": costs.get("month", 0),
        "month_inr": round(costs.get("month", 0) * inr_rate, 2)
    }
