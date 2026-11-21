"""Causal market structure and indicators computed from closed bars."""

import os
from statistics import fmean, pstdev

from backend.market import Candle

INDICATOR_DEFAULTS = {
    "MARKET_RSI_PERIOD": 14, "MARKET_ATR_PERIOD": 14, "MARKET_MA_PERIOD": 20,
    "MARKET_VOLUME_PERIOD": 20, "MARKET_MACD_FAST": 12, "MARKET_MACD_SLOW": 26,
    "MARKET_MACD_SIGNAL": 9, "MARKET_BOLLINGER_WIDTH": 2,
}
STRUCTURE_DEFAULTS = {
    "MARKET_SWING_RADIUS": 2, "MARKET_EQUAL_TOLERANCE": 0.001, "MARKET_MSS_RANGE_MULTIPLE": 1,
    "MARKET_BLOCK_LOOKBACK": 10, "MARKET_FALSE_BREAKOUT_BARS": 3, "MARKET_MSS_LOOKBACK": 14,
    "MARKET_MIN_FVG_RELATIVE": 0,
}


def ema_series(values, period):
    series = [values[0]]
    alpha = 2 / (period + 1)
    for value in values[1:]:
        series.append(series[-1] + alpha * (value - series[-1]))
    return series


def analyze(bars: list[Candle], swing: int | None = None, tolerance: float | None = None):
    swing = swing if swing is not None else max(1, int(os.getenv("MARKET_SWING_RADIUS", "2")))
    tolerance = tolerance if tolerance is not None else max(0, float(os.getenv("MARKET_EQUAL_TOLERANCE", "0.001")))
    mss_multiple = max(0, float(os.getenv("MARKET_MSS_RANGE_MULTIPLE", "1")))
    block_lookback = max(1, int(os.getenv("MARKET_BLOCK_LOOKBACK", "10")))
    false_window = max(1, int(os.getenv("MARKET_FALSE_BREAKOUT_BARS", "3")))
    mss_lookback = max(1, int(os.getenv("MARKET_MSS_LOOKBACK", "14")))
    gap_threshold = max(0, float(os.getenv("MARKET_MIN_FVG_RELATIVE", "0")))
    if swing < 1 or tolerance < 0:
        raise ValueError("Invalid detector parameters")
    events = []
    highs, lows = [], []
    broken = set()
    breaks = {}
    gaps = []
    blocks = []
    trend = "lateral"
    for i, bar in enumerate(bars):
        def event(kind, side, level, **details):
            events.append(dict(kind=kind, side=side, level=level, time=bar.time, confirmed_at=bar.close_time, state="confirmado", **details))

        for side, (level, opened) in list(breaks.items()):
            if i - opened > false_window:
                del breaks[side]
            elif (bar.close <= level if side == "alcista" else bar.close >= level):
                event("False Breakout", "bajista" if side == "alcista" else "alcista",
                      level, origin=bars[opened].time)
                del breaks[side]

        for block in blocks:
            if block["state"] == "invalidado":
                continue
            bullish = block["side"] == "alcista"
            invalid = bar.close < block["low"] if bullish else bar.close > block["high"]
            if invalid:
                block["state"] = "invalidado"
                event("Breaker Block", "bajista" if bullish else "alcista",
                      block["low"], high=block["high"], origin=block["origin"])
            elif block["state"] == "abierto" and bar.low <= block["high"] and bar.high >= block["low"]:
                block["state"] = "mitigado"
                event("Mitigation Block", block["side"], block["low"],
                      high=block["high"], origin=block["origin"])

        pivot = i - swing
        if pivot >= swing:
            candidate = bars[pivot]
            window = bars[pivot - swing:i + 1]
            for side, key, levels, sign in (("alcista", "high", highs, 1),
                                             ("bajista", "low", lows, -1)):
                level = getattr(candidate, key)
                if all(sign * level > sign * getattr(other, key) for other in window if other is not candidate):
                    event("Swing High" if sign == 1 else "Swing Low", side, level, origin=candidate.time)
                    if levels:
                        previous = levels[-1][1]
                        if abs(level - previous) <= abs(previous) * tolerance:
                            event("Equal Highs" if sign == 1 else "Equal Lows", side, level)
                        else:
                            event(("HH" if level > previous else "LH") if sign == 1 else
                                  ("HL" if level > previous else "LL"), side, level)
                    levels.append((pivot, level))
        for side, levels, sign, wick in (("alcista", highs, 1, bar.high),
                                          ("bajista", lows, -1, bar.low)):
            if not levels:
                continue
            origin, level = levels[-1]
            key = (side, origin)
            if key in broken or sign * (wick - level) <= 0:
                continue
            if sign * (bar.close - level) > 0:
                kind = "BOS" if trend in ("lateral", side) else "CHoCH"
                if kind == "CHoCH" and i > 1 and abs(bar.close - bar.open) > mss_multiple * fmean(
                    item.high - item.low for item in bars[max(0, i - mss_lookback):i]
                ):
                    event("MSS", side, level)
                event(kind, side, level)
                opposing = next((item for item in reversed(bars[max(0, i - block_lookback):i])
                                 if sign * (item.close - item.open) < 0), None)
                if opposing:
                    block = dict(side=side, low=opposing.low, high=opposing.high,
                                 state="abierto", time=bar.time, origin=opposing.time)
                    blocks.append(block)
                    event("Order Block", side, opposing.low, high=opposing.high, origin=opposing.time)
                breaks[side] = (level, i)
                broken.add(key)
                trend = side
            else:
                event("Liquidity Sweep", "bajista" if sign == 1 else "alcista", level)
        for gap in gaps:
            if gap["state"] == "invalidado":
                continue
            bull = gap["side"] == "alcista"
            if (bull and bar.close < gap["low"]) or (not bull and bar.close > gap["high"]):
                gap["state"] = "invalidado"
                event("IFVG", "bajista" if bull else "alcista", gap["low"], high=gap["high"])
            elif gap["state"] == "abierto" and bar.low <= gap["high"] and bar.high >= gap["low"]:
                gap["state"] = "mitigado"
        if i >= 2:
            previous = bars[i - 2]
            if bar.low - previous.high > abs(previous.high) * gap_threshold:
                gaps.append(dict(side="alcista", low=previous.high, high=bar.low,
                                 state="abierto", time=bar.time))
                event("FVG", "alcista", previous.high, high=bar.low)
            elif previous.low - bar.high > abs(previous.low) * gap_threshold:
                gaps.append(dict(side="bajista", low=bar.high, high=previous.low,
                                 state="abierto", time=bar.time))
                event("FVG", "bajista", bar.high, high=previous.low)
    support = lows[-1][1] if lows else None
    resistance = highs[-1][1] if highs else None
    provisional = []
    for i in range(max(swing, len(bars) - swing), len(bars)):
        for key, sign, kind in (("high", 1, "Swing High"), ("low", -1, "Swing Low")):
            level = getattr(bars[i], key)
            if all(sign * level > sign * getattr(bars[j], key)
                   for j in range(i - swing, len(bars)) if j != i):
                provisional.append(dict(kind=kind, level=level, time=bars[i].time,
                                        state="provisional", confirmed_at=None))
    equilibrium = (support + resistance) / 2 if support is not None and resistance is not None and support < resistance else None
    return dict(trend=trend, support=support, resistance=resistance, equilibrium=equilibrium,
                premium=[equilibrium, resistance] if equilibrium is not None else None,
                discount=[support, equilibrium] if equilibrium is not None else None,
                provisional=provisional,
                events=events, gaps=gaps, blocks=blocks,
                buy_side_liquidity=resistance, sell_side_liquidity=support,
                indicators=indicators(bars))


def indicator_parameters():
    periods = {key: max(1, min(149, int(os.getenv(key, str(default)))))
               for key, default in INDICATOR_DEFAULTS.items() if key != "MARKET_BOLLINGER_WIDTH"}
    periods["MARKET_BOLLINGER_WIDTH"] = max(0, min(10, float(os.getenv("MARKET_BOLLINGER_WIDTH", "2"))))
    if periods["MARKET_MACD_FAST"] >= periods["MARKET_MACD_SLOW"]:
        raise ValueError("MACD rápido debe ser inferior al lento")
    return periods


def indicators(bars):
    config = indicator_parameters()
    rsi_period, atr_period = config["MARKET_RSI_PERIOD"], config["MARKET_ATR_PERIOD"]
    ma_period, volume_period = config["MARKET_MA_PERIOD"], config["MARKET_VOLUME_PERIOD"]
    fast, slow, signal = config["MARKET_MACD_FAST"], config["MARKET_MACD_SLOW"], config["MARKET_MACD_SIGNAL"]
    warmup = max(35, rsi_period + 1, atr_period + 1, ma_period, volume_period + 1, slow + signal - 1)
    if len(bars) < warmup:
        return {}
    closes = [bar.close for bar in bars]
    changes = [right - left for left, right in zip(closes, closes[1:])][-rsi_period:]
    gains = sum(max(change, 0) for change in changes)
    losses = sum(max(-change, 0) for change in changes)
    center = fmean(closes[-ma_period:])
    width = config["MARKET_BOLLINGER_WIDTH"] * pstdev(closes[-ma_period:])
    volume = sum(bar.volume for bar in bars)
    macd_series = [first - second for first, second in zip(ema_series(closes, fast), ema_series(closes, slow))][slow-1:]
    return dict(
        sma=center, ema=ema_series(closes, ma_period)[-1], macd=macd_series[-1], macd_signal=ema_series(macd_series, signal)[-1],
        rsi=100 * gains / (gains + losses) if gains + losses else 50,
        atr=fmean(max(bar.high - bar.low, abs(bar.high - before.close), abs(bar.low - before.close))
                  for before, bar in zip(bars[-atr_period-1:-1], bars[-atr_period:])),
        bollinger=[center - width, center + width], volume=bars[-1].volume,
        relative_volume=bars[-1].volume / baseline if (baseline := fmean(bar.volume for bar in bars[-volume_period-1:-1])) else None,
        vwap=sum((bar.high + bar.low + bar.close) / 3 * bar.volume for bar in bars) / volume if volume else None,
    )


def chart_indicators(bars):
    lines = {name: [] for name in ("EMA", "SMA", "VWAP", "Bollinger superior", "Bollinger inferior")}
    if not bars:
        return lines
    config = indicator_parameters()
    period = config["MARKET_MA_PERIOD"]
    closes = [bar.close for bar in bars]
    averages = ema_series(closes, period)
    value = volume = 0.0
    for index, bar in enumerate(bars):
        lines["EMA"].append({"time": bar.time, "value": averages[index]})
        value += (bar.high + bar.low + bar.close) / 3 * bar.volume
        volume += bar.volume
        if volume:
            lines["VWAP"].append({"time": bar.time, "value": value / volume})
        if index + 1 >= period:
            window = closes[index + 1 - period:index + 1]
            center = fmean(window)
            width = config["MARKET_BOLLINGER_WIDTH"] * pstdev(window)
            for name, level in (("SMA", center), ("Bollinger superior", center + width),
                                ("Bollinger inferior", center - width)):
                lines[name].append({"time": bar.time, "value": level})
    return lines
