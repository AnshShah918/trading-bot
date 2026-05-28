from src.indicators.market_indicators import (
    MarketIndicators
)
from src.config.settings import (
    DEFAULT_POSITION_SIZE,
    MIN_VIABLE_TRADE
)

TARGET_RISK_REWARD = 2.0


class MomentumScanner:

    def scan(
        self,
        symbol,
        candles,
        available_capital=None
    ):

        recent_high = (
            MarketIndicators.recent_high(
                candles
            )
        )

        avg_volume = (
            MarketIndicators.average_volume(
                candles
            )
        )

        momentum = (
            MarketIndicators.momentum(
                candles
            )
        )

        ma20 = (
            MarketIndicators.moving_average(
                candles,
                20
            )
        )

        ma50 = (
            MarketIndicators.moving_average(
                candles,
                50
            )
        )

        rsi = (
            MarketIndicators.rsi(
                candles
            )
        )

        atr = (
            MarketIndicators.atr(
                candles
            )
        )

        fifty_two_high = (
            MarketIndicators.fifty_two_week_high(
                candles
            )
        )

        current_price = candles[-1]["close"]
        current_volume = candles[-1]["volume"]

        breakout_distance = (
            current_price / recent_high
        )

        volume_ratio = (
            current_volume / avg_volume
        )

        trend_spread = (
            (ma20 - ma50) / ma50
        )

        high_proximity = (
            current_price / fifty_two_high
        )

        atr_multiplier = 1.5

        suggested_stop = round(
            current_price - (atr * atr_multiplier),
            2
        )

        risk_per_share = (
            current_price - suggested_stop
        )

        risk_pct = (
            risk_per_share / current_price * 100
        )

        # Target price — 1:2 risk reward
        target_price = round(
            current_price + (risk_per_share * TARGET_RISK_REWARD),
            2
        )

        target_pct = round(
            (target_price - current_price)
            / current_price * 100,
            2
        )

        # Capital-aware position sizing
        if available_capital is None:
            position_capital = 2000
        else:
            position_capital = (
                available_capital * DEFAULT_POSITION_SIZE
            )

        shares_to_buy = (
            int(position_capital / current_price)
            if risk_per_share > 0
            and position_capital >= MIN_VIABLE_TRADE
            else 0
        )

        trade_value = round(
            shares_to_buy * current_price, 2
        )

        breakout = (
            breakout_distance >= 0.95
        )

        trend_quality = (
            current_price > ma20 > ma50
        )

        near_high = (
            high_proximity >= 0.95
        )

        decent_volume = (
            volume_ratio >= 1.2
        )

        overbought = (
            rsi > 70
        )

        untradeable = (
            shares_to_buy == 0
            or risk_pct > 6.0
        )

        score = 0

        # Momentum
        if momentum >= 0.50:
            score += 30
        elif momentum >= 0.30:
            score += 25
        elif momentum >= 0.15:
            score += 15
        elif momentum >= 0.05:
            score += 8

        # Breakout
        if breakout_distance >= 0.99:
            score += 20
        elif breakout_distance >= 0.97:
            score += 15
        elif breakout_distance >= 0.95:
            score += 8

        # Trend
        if trend_spread >= 0.10:
            score += 20
        elif trend_spread >= 0.05:
            score += 10

        # High proximity
        if high_proximity >= 0.98:
            score += 20
        elif high_proximity >= 0.95:
            score += 15
        elif high_proximity >= 0.90:
            score += 8

        # Volume
        if volume_ratio >= 2:
            score += 20
        elif volume_ratio >= 1.5:
            score += 12
        elif volume_ratio >= 1.2:
            score += 6

        # RSI
        if 55 <= rsi <= 70:
            score += 15
        elif 45 <= rsi < 55:
            score += 5
        elif rsi > 70:
            score -= 15
        elif rsi < 40:
            score -= 10

        if (
            score >= 85
            and breakout
            and trend_quality
            and near_high
            and decent_volume
            and not overbought
            and not untradeable
        ):
            tier = "STRONG"

        elif score >= 45:
            tier = "WATCH"

        else:
            tier = "REJECT"

        return {
            "symbol": symbol,
            "momentum": round(momentum, 3),
            "rsi": round(rsi, 1),
            "atr": round(atr, 2),
            "suggested_stop": suggested_stop,
            "target_price": target_price,
            "target_pct": target_pct,
            "risk_pct": round(risk_pct, 2),
            "risk_per_share": round(risk_per_share, 2),
            "shares_to_buy": shares_to_buy,
            "trade_value": trade_value,
            "breakout_distance": round(breakout_distance, 3),
            "trend_spread": round(trend_spread, 3),
            "volume_ratio": round(volume_ratio, 2),
            "high_proximity": round(high_proximity, 3),
            "score": score,
            "tier": tier
        }
