from src.indicators.market_indicators import (
    MarketIndicators
)


class MomentumScanner:

    def scan(
        self,
        symbol,
        candles,
        portfolio_capital=50000,
        risk_per_trade_pct=0.01
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

        current_price = (
            candles[-1]["close"]
        )

        current_volume = (
            candles[-1]["volume"]
        )

        breakout_distance = (
            current_price
            /
            recent_high
        )

        volume_ratio = (
            current_volume
            /
            avg_volume
        )

        trend_spread = (
            (
                ma20
                -
                ma50
            )
            /
            ma50
        )

        high_proximity = (
            current_price
            /
            fifty_two_high
        )

        breakout = (
            breakout_distance
            >=
            0.95
        )

        trend_quality = (
            current_price
            >
            ma20
            >
            ma50
        )

        near_high = (
            high_proximity
            >=
            0.95
        )

        decent_volume = (
            volume_ratio
            >=
            1.2
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
        elif 70 < rsi <= 80:
            score += 0
        elif rsi > 80:
            score -= 10
        elif rsi < 40:
            score -= 10

        # Portfolio Risk Engine

        capital_at_risk = (
            portfolio_capital
            *
            risk_per_trade_pct
        )

        suggested_stop = (
            current_price
            -
            (
                atr
                *
                1.5
            )
        )

        risk_per_share = (
            current_price
            -
            suggested_stop
        )

        risk_pct = (
            risk_per_share
            /
            current_price
        ) * 100

        shares_to_buy = (
            capital_at_risk
            /
            risk_per_share
        )

        affordable = (
            shares_to_buy
            >=
            1
        )

        if (
            score >= 85
            and breakout
            and trend_quality
            and near_high
            and decent_volume
        ):
            tier = "STRONG"

        elif score >= 45:
            tier = "WATCH"

        else:
            tier = "REJECT"

        return {
            "symbol": symbol,
            "momentum": round(
                momentum,
                3
            ),
            "rsi": round(
                rsi,
                1
            ),
            "atr": round(
                atr,
                2
            ),
            "capital_at_risk": round(
                capital_at_risk,
                2
            ),
            "suggested_stop": round(
                suggested_stop,
                2
            ),
            "risk_pct": round(
                risk_pct,
                2
            ),
            "risk_per_share": round(
                risk_per_share,
                2
            ),
            "shares_to_buy": int(
                shares_to_buy
            ),
            "affordable": affordable,
            "breakout_distance": round(
                breakout_distance,
                3
            ),
            "trend_spread": round(
                trend_spread,
                3
            ),
            "volume_ratio": round(
                volume_ratio,
                2
            ),
            "high_proximity": round(
                high_proximity,
                3
            ),
            "score": score,
            "tier": tier
        }
