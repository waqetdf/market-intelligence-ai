"""Deterministic confluence and closed-bar replay."""

from backend.technical import analyze


def opportunity(bars, context, current):
    result = {"direction": "sin señal", "evidence": [], "risks": [], "invalidation": None,
              "target": None, "reward_risk": None}
    if len(bars) < 35 or context is None or not context["indicators"]:
        result["risks"].append("Histórico o contexto insuficiente")
        return result
    trend = current["trend"]
    recent = {bar.time for bar in bars[-5:]}
    structure = [event for event in current["events"] if event["time"] in recent
                 and event["side"] == trend and event["kind"] in ("BOS", "CHoCH")]
    if not structure or context["trend"] != trend:
        result["risks"].append("Sin ruptura reciente alineada con la temporalidad superior")
        return result
    relative_volume = current["indicators"]["relative_volume"]
    if relative_volume is None or relative_volume < 1:
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
                  evidence=[structure[-1]["kind"], "Tendencia superior alineada", "Volumen relativo ≥ 1"],
                  invalidation=stop, target=target,
                  reward_risk=abs(target - price) / abs(price - stop) if target is not None else None)
    if target is None:
        result["risks"].append("Sin objetivo justificado por un swing superior")
    return result


def replay(bars, higher, fee_bps=10, slippage_bps=5):
    """At each close, simulate one next-bar holding period using its open and close."""
    returns = []
    for i in range(35, len(bars)):
        history = bars[max(0, i - 150):i]
        context = [bar for bar in higher if bar.close_time <= history[-1].close_time][-150:]
        if len(context) < 35 or bars[i].time < history[-1].close_time:
            continue
        signal = opportunity(history, analyze(context), analyze(history))
        if signal["direction"] == "sin señal":
            continue
        trade = bars[i]
        if trade.open <= 0:
            continue
        sign = 1 if signal["direction"] == "posible compra" else -1
        returns.append(sign * (trade.close / trade.open - 1) - 2 * (fee_bps + slippage_bps) / 10000)
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
            "maximum_drawdown": drawdown if returns else None}
