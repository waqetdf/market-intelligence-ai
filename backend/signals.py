"""Deterministic confluence and closed-bar replay."""

import os

from backend.technical import analyze


def opportunity(bars, context, current, frames=None):
    window = max(1, int(os.getenv("MARKET_STRUCTURE_WINDOW", "5")))
    volume_min = max(0, float(os.getenv("MARKET_RELATIVE_VOLUME_MIN", "1")))
    result = {"direction": "sin señal", "evidence": [], "risks": [], "invalidation": None,
              "target": None, "reward_risk": None}
    if len(bars) < 35 or context is None or not context["indicators"]:
        result["risks"].append("Histórico o contexto insuficiente")
        return result
    trend = current["trend"]
    recent = {bar.time for bar in bars[-window:]}
    structure = [event for event in current["events"] if event["time"] in recent
                 and event["side"] == trend and event["kind"] in ("BOS", "CHoCH")]
    if not structure or context["trend"] != trend:
        result["risks"].append("Sin ruptura reciente alineada con la temporalidad superior")
        return result
    relative_volume = current["indicators"]["relative_volume"]
    if relative_volume is None or relative_volume < volume_min:
        result["risks"].append("Volumen relativo insuficiente")
        return result
    bullish = trend == "alcista"
    price = bars[-1].close
    stop = current["support"] if bullish else current["resistance"]
    if stop is None or (bullish and stop >= price) or (not bullish and stop <= price):
        result["risks"].append("Falta un nivel de invalidación válido")
        return result
    levels = [event["level"] for event in context["events"]
              if event["kind"] == ("Swing High" if bullish else "Swing Low")
              and (event["level"] > price if bullish else event["level"] < price)]
    target = (min(levels) if bullish else max(levels)) if levels else None
    result.update(trigger_time=structure[-1]["time"], direction="posible compra" if bullish else "posible venta",
                  evidence=[structure[-1]["kind"], "Tendencia superior alineada", f"Volumen relativo {relative_volume:.2f} ≥ {volume_min:g}"],
                  invalidation=stop, target=target,
                  reward_risk=abs(target - price) / abs(price - stop) if target is not None else None)
    if target is None:
        result["risks"].append("Sin objetivo justificado por un swing superior")
    result["patterns"] = [structure[-1]]
    result["quality"] = {"status": "sin calibrar"}
    atr = current["indicators"].get("atr")
    if atr and abs(price - stop) > 3 * atr:
        result["risks"].append("Invalidación a más de tres ATR")
    for interval, report in (frames or {}).items():
        if interval in ("1h", "1d", "1w") and report["trend"] not in ("lateral", trend):
            result["risks"].append(f"Tendencia contraria en {interval}")
    for frame, kind in (("5m", "FVG"), ("15m", "Liquidity Sweep")):
        report = (frames or {}).get(frame, current if frame == "15m" else {})
        if kind == "FVG":
            match = next((gap for gap in reversed(report.get("gaps", []))
                          if gap["state"] == "abierto" and gap["side"] == trend), None)
        else:
            match = next((event for event in reversed(report.get("events", []))
                          if event["kind"] == kind and event["side"] == trend and event["time"] in recent), None)
        if match:
            result["patterns"].append(dict(match, kind=kind, timeframe=frame))
            result["evidence"].append(f"{kind} concordante en {frame}")
            if kind == "FVG":
                result["interest_zone"] = [match["low"], match["high"]]
    return result


def replay(bars, higher, fee_bps=10, slippage_bps=5):
    """At each close, simulate one next-bar holding period using its open and close."""
    trades = []
    eligible = []
    for i in range(35, len(bars)):
        history = bars[max(0, i - 150):i]
        context = [bar for bar in higher if bar.close_time <= history[-1].close_time][-150:]
        if len(context) < 35 or bars[i].time < history[-1].close_time:
            continue
        eligible.append(i)
        signal = opportunity(history, analyze(context), analyze(history))
        if signal["direction"] == "sin señal":
            continue
        trade = bars[i]
        if trade.open <= 0:
            continue
        sign = 1 if signal["direction"] == "posible compra" else -1
        value = sign * (trade.close / trade.open - 1) - 2 * (fee_bps + slippage_bps) / 10000
        trades.append((i, value, signal["reward_risk"]))
    overall = metrics(trades)
    if len(eligible) < 20:
        return {**overall, "out_of_sample": None, "walk_forward": []}
    holdout = eligible[len(eligible) * 3 // 4]
    folds = []
    for start in range(1, 4):
        lower = eligible[len(eligible) * start // 4]
        upper = eligible[len(eligible) * (start + 1) // 4] if start < 3 else len(bars)
        folds.append({"start": bars[lower].time, "end": bars[upper - 1].close_time,
                      **metrics([trade for trade in trades if lower <= trade[0] < upper])})
    return {**overall, "out_of_sample": metrics([trade for trade in trades if trade[0] >= holdout]),
            "walk_forward": folds}


def metrics(trades):
    returns = [trade[1] for trade in trades]
    ratios = [trade[2] for trade in trades if trade[2] is not None]
    profits = sum(value for value in returns if value > 0)
    losses = -sum(value for value in returns if value < 0)
    equity = peak = 1.0
    drawdown = 0.0
    for value in returns:
        equity *= max(0, 1 + value)
        peak = max(peak, equity)
        drawdown = max(drawdown, 1 - equity / peak)
    return {"mode": "simulación a una vela", "count": len(returns),
            "win_rate": sum(value > 0 for value in returns) / len(returns) if returns else None,
            "profit_factor": profits / losses if losses else None,
            "expectancy": sum(returns) / len(returns) if returns else None,
            "maximum_drawdown": drawdown if returns else None,
            "mean_signal_reward_risk": sum(ratios) / len(ratios) if ratios else None}
