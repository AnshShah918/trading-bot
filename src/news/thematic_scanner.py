import os
import json
import time
from google import genai
from google.genai import types
from datetime import date
from src.universe.nifty500 import Nifty500

THEMATIC_COST_FILE = "data/thematic_costs.json"
MAX_RETRIES = 2


def load_costs():
    try:
        with open(THEMATIC_COST_FILE) as f:
            return json.load(f)
    except Exception:
        return {
            "today_calls": 0,
            "month_calls": 0,
            "date": ""
        }


def save_costs(costs):
    os.makedirs("data", exist_ok=True)
    with open(THEMATIC_COST_FILE, "w") as f:
        json.dump(costs, f)


def track_call():
    costs = load_costs()
    today = date.today().isoformat()
    if costs.get("date") != today:
        costs["today_calls"] = 0
        costs["date"] = today
    costs["today_calls"] += 1
    costs["month_calls"] += 1
    save_costs(costs)


def get_nifty500_set():
    try:
        symbols = Nifty500.load()
        return set(symbols)
    except Exception:
        return set()


def search_news_and_themes():
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return None

    client = genai.Client(api_key=api_key)
    today = date.today().strftime("%d %B %Y")

    prompt = f"""
Today is {today}.

Search for the latest Indian stock market news and
identify 2-3 major themes or events that could
impact specific stocks or sectors.

Focus on:
- Government policy announcements
- Major deals (mergers, acquisitions, JVs, MoUs)
- Sector news (nuclear, defence, EV, infra, pharma)
- Global events affecting Indian companies
- PLI schemes, budget allocations
- Major contracts won or lost

For each theme:
1. Name the theme clearly
2. Explain why it matters for stocks
3. List 3-5 specific NSE stock symbols
4. Rate urgency: HIGH, MEDIUM or LOW

Respond ONLY in this exact JSON format with no
extra text before or after:
[
  {{
    "theme": "Theme name",
    "summary": "2-3 sentence explanation",
    "urgency": "HIGH",
    "stocks": ["SYMBOL1", "SYMBOL2"],
    "source_hint": "What to search to verify"
  }}
]
"""

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[
                        types.Tool(
                            google_search=(
                                types.GoogleSearch()
                            )
                        )
                    ]
                )
            )

            track_call()
            return response.text

        except Exception as e:
            print(f"News search attempt {attempt + 1} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(3)

    return None


def parse_themes(raw):
    if not raw:
        return []

    try:
        cleaned = raw.strip()

        if "```" in cleaned:
            parts = cleaned.split("```")
            for part in parts:
                part = part.replace("json", "").strip()
                if part.startswith("["):
                    cleaned = part
                    break

        start = cleaned.find("[")
        end = cleaned.rfind("]") + 1

        if start == -1 or end == 0:
            return []

        cleaned = cleaned[start:end]
        return json.loads(cleaned)

    except Exception as e:
        print(f"Theme parse error: {e}")
        return []


def cross_reference_universe(themes):
    nifty500 = get_nifty500_set()

    if not nifty500:
        return themes

    for theme in themes:
        stocks = theme.get("stocks", [])
        theme["stocks_in_universe"] = [
            s for s in stocks if s in nifty500
        ]
        theme["stocks_watch_only"] = [
            s for s in stocks if s not in nifty500
        ]

    return themes


def get_thematic_alerts():
    raw = search_news_and_themes()

    if raw is None:
        return None, "AI search unavailable"

    themes = parse_themes(raw)

    if not themes:
        return [], "No significant themes today"

    themes = cross_reference_universe(themes)

    urgency_order = {
        "HIGH": 0, "MEDIUM": 1, "LOW": 2
    }
    themes.sort(
        key=lambda x: urgency_order.get(
            x.get("urgency", "LOW"), 2
        )
    )

    return themes, None


def escape_md(text):
    # Escape special Markdown characters
    chars = [
        '_', '*', '[', ']', '(', ')',
        '~', '`', '>', '#', '+', '-',
        '=', '|', '{', '}', '.', '!'
    ]
    for c in chars:
        text = text.replace(c, f"\\{c}")
    return text


def format_theme_message(theme):
    urgency = theme.get("urgency", "LOW")

    urgency_emoji = {
        "HIGH": "🔴",
        "MEDIUM": "🟡",
        "LOW": "🟢"
    }.get(urgency, "⚪")

    in_universe = theme.get(
        "stocks_in_universe", []
    )
    watch_only = theme.get("stocks_watch_only", [])

    # Escape theme name and summary
    theme_name = escape_md(
        theme.get("theme", "")
    )
    summary = escape_md(
        theme.get("summary", "")
    )
    source = escape_md(
        theme.get("source_hint", "")
    )

    stocks_line = ""

    if in_universe:
        stocks_line += (
            f"✅ In Nifty 500: "
            f"{', '.join(in_universe)}\n"
        )

    if watch_only:
        stocks_line += (
            f"👁 Watch only: "
            f"{', '.join(watch_only)}\n"
        )

    return (
        f"{urgency_emoji} *{theme_name}*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{summary}\n\n"
        f"{stocks_line}"
        f"🔍 Verify: {source}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Research before trading\\.\n"
        f"Use /scan after you've verified\\."
    )
