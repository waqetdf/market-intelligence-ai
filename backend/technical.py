"""Causal market structure and indicators computed from closed bars."""

from statistics import fmean, pstdev

from backend.market import Candle


def ema(values, period):
    result = values[0]
    for value in values[1:]:
        result += 2 / (period + 1) * (value - result)
    return result


def analyze(bars: list[Candle], swing: int = 2, tolerance: float = 0.001):
    events = []
    highs, lows = [], []
    broken = set()
    gaps = []
    trend = "lateral"
    for i, bar in enumerate(bars):
        def event(kind, side, level, **details):
            events.append(dict(kind=kind, side=side, level=level, time=bar.time, **details))

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
                if kind == "CHoCH" and i > 1 and abs(bar.close - bar.open) > fmean(
                    item.high - item.low for item in bars[max(0, i - 14):i]
                ):
                    event("MSS", side, level)
                event(kind, side, level)
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
            if bar.low > previous.high:
                gaps.append(dict(side="alcista", low=previous.high, high=bar.low,
                                 state="abierto", time=bar.time))
                event("FVG", "alcista", previous.high, high=bar.low)
            elif bar.high < previous.low:
                gaps.append(dict(side="bajista", low=bar.high, high=previous.low,
                                 state="abierto", time=bar.time))
                event("FVG", "bajista", bar.high, high=previous.low)
    support = lows[-1][1] if lows else None
    resistance = highs[-1][1] if highs else None
    return dict(trend=trend, support=support, resistance=resistance,
                equilibrium=(support + resistance) / 2 if support is not None and resistance is not None else None,
                events=events, gaps=gaps, indicators=indicators(bars))


def indicators(bars):
    if len(bars) < 35:
        return {}
    closes = [bar.close for bar in bars]
    changes = [right - left for left, right in zip(closes, closes[1:])][-14:]
    gains = sum(max(change, 0) for change in changes)
    losses = sum(max(-change, 0) for change in changes)
    center = fmean(closes[-20:])
    width = 2 * pstdev(closes[-20:])
    volume = sum(bar.volume for bar in bars)
    macd_series = [ema(closes[:i], 12) - ema(closes[:i], 26) for i in range(26, len(closes) + 1)]
    return dict(
        sma=center, ema=ema(closes, 20), macd=macd_series[-1], macd_signal=ema(macd_series, 9),
        rsi=100 * gains / (gains + losses) if gains + losses else 50,
        atr=fmean(max(bar.high - bar.low, abs(bar.high - before.close), abs(bar.low - before.close))
                  for before, bar in zip(bars[-15:-1], bars[-14:])),
        bollinger=[center - width, center + width], volume=bars[-1].volume,
        relative_volume=bars[-1].volume / baseline if (baseline := fmean(bar.volume for bar in bars[-21:-1])) else None,
        vwap=sum((bar.high + bar.low + bar.close) / 3 * bar.volume for bar in bars) / volume if volume else None,
    )
