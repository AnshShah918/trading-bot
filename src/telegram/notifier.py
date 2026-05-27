import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def format_setup(result):

    ai_line = ""
    if result.get("ai_confidence"):
        ai_line = (
            f"🤖 AI:    {result['ai_confidence']}/10\n"
            f"💬 {result.get('ai_reasoning', '')}\n"
        )

    return (
        f"🟢 *{result['symbol']}*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Score:    {result['score']}\n"
        f"RSI:      {result['rsi']}\n"
        f"Momentum: {result['momentum']}\n"
        f"Volume:   {result['volume_ratio']}x avg\n"
        f"{ai_line}"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Entry:    ₹{result['current_price']}\n"
        f"Stop:     ₹{result['suggested_stop']} ({result['risk_pct']}% risk)\n"
        f"Shares:   {result['shares_to_buy']}\n"
        f"Capital:  ₹{round(result['current_price'] * result['shares_to_buy'], 2)}"
    )


def build_keyboard(symbol):

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ YES — Open Trade",
                callback_data=f"YES:{symbol}"
            ),
            InlineKeyboardButton(
                "❌ NO — Skip",
                callback_data=f"NO:{symbol}"
            )
        ]
    ])


async def send_setup(bot, result):

    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    await bot.send_message(
        chat_id=chat_id,
        text=format_setup(result),
        parse_mode="Markdown",
        reply_markup=build_keyboard(
            result["symbol"]
        )
    )


async def send_message(bot, text):

    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    await bot.send_message(
        chat_id=chat_id,
        text=text
    )
