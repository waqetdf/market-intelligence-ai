"""Deterministic confluence and closed-bar replay."""

from bisect import bisect_right
from math import sqrt
import os

from pydantic import BaseModel, Field

from backend.market import INTERVALS

from backend.technical import analyze, indicator_parameters, STRUCTURE_DEFAULTS


CONTEXT_FRAMES = dict(zip(INTERVALS, ("15m", "1h", "4h", "4h", "4h", "1d", "1w", None)))
STRATEGY_VERSION = 1
class Strategy(BaseModel):
    window: int = Field(ge=1, le=50)
    volume_min: float = Field(ge=0, le=20, allow_inf_nan=False)
    require_sweep: bool = False
    require_fvg: bool = False
    max_stop_atr: float = Field(default=0, ge=0, le=20, allow_inf_nan=False)
    macro_pause_minutes: int = Field(default=0, ge=0, le=180)


def default_strategy():
    return Strategy(window=int(os.getenv("MARKET_STRUCTURE_WINDOW", "5")),
                    volume_min=float(os.getenv("MARKET_RELATIVE_VOLUME_MIN", "1")))


def strategy_signature(rules):
    return {"version": STRATEGY_VERSION, "rules": rules.model_dump(),
            "detectors": {key: os.getenv(key, str(default)) for key, default in STRUCTURE_DEFAULTS.items()},
            "indicators": indicator_parameters()}


def assess_quality(report, as_of, signature):
    if (not report or signature["rules"]["macro_pause_minutes"]
            or report.get("bar_end") is None or report["bar_end"] > as_of or report["created_at"] > as_of
            or report["strategy"] != signature):
        return {"status": "sin calibrar"}
    sample = report.get("out_of_sample") or {}
    size = sample.get("count", 0)
    if size < 50:
        return {"status": "muestra insuficiente", "sample": size}
    precision = sample["precision"]
    z = 1.96
    lower = (precision + z*z/(2*size) - z*sqrt((precision*(1-precision) + z*z/(4*size))/size))/(1+z*z/size)
    supported = sample["expectancy"] > 0 and lower > .5
    return {"status": "respaldo histórico preliminar" if supported else "respaldo histórico bajo",
            "sample": size, "simulation_id": report["id"]}


def opportunity(bars, context, current, frames=None, rules=None, interval="15m"):
    rules = rules or default_strategy()
    window = rules.window
    volume_min = rules.volume_min
    result = {"direction": "sin señal", "evidence": [], "risks": [], "invalidation": None,
              "target": None, "reward_risk": None}
    if len(bars) < 35 or context is None or not context["indicators"] or not current["indicators"]:
        result["risks"].append("Histórico o contexto insuficiente")
        return result
    trend = current["trend"]
    recent = {bar.time for bar in bars[-window:]}
    invalidated = {event["origin"] for event in current["events"] if event["kind"] == "False Breakout"}
    structure = [event for event in current["events"] if event["time"] in recent
                 and event["time"] not in invalidated and event["kind"] in ("BOS", "CHoCH")
                 and event["side"] == trend]
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
    sweep = next((event for event in reversed(current["events"])
                  if event["kind"] == "Liquidity Sweep" and event["side"] == trend and event["time"] in recent), None)
    if rules.require_sweep and not sweep:
        result["risks"].append("Falta un barrido de liquidez concordante")
        return result
    atr = current["indicators"].get("atr")
    if rules.max_stop_atr and (not atr or abs(price - stop) > rules.max_stop_atr * atr):
        result["risks"].append("Invalidación fuera del límite de volatilidad")
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
    if atr and abs(price - stop) > 3 * atr:
        result["risks"].append("Invalidación a más de tres ATR")
    for interval, report in (frames or {}).items():
        if interval in ("1h", "1d", "1w") and report["trend"] not in ("lateral", trend):
            result["risks"].append(f"Tendencia contraria en {interval}")
    if sweep:
        result["patterns"].append(dict(sweep, timeframe=interval))
        result["evidence"].append(f"Barrido concordante en {interval}")
    fvg = next((gap for gap in reversed((frames or {}).get("5m", {}).get("gaps", []))
                if gap["state"] == "abierto" and gap["side"] == trend), None)
    if rules.require_fvg and not fvg:
        return {"direction": "sin señal", "evidence": [], "risks": ["Falta un FVG abierto concordante en 5m"],
                "invalidation": None, "target": None, "reward_risk": None}
    if fvg:
        result["patterns"].append(dict(fvg, kind="FVG", timeframe="5m"))
        result["evidence"].append("FVG concordante en 5m")
        result["interest_zone"] = [fvg["low"], fvg["high"]]
    return result


def replay(bars, higher, fee_bps=10, slippage_bps=5, interval="15m", rules=None, lower=None):
    """At each close, simulate one next-bar holding period using its open and close."""
    rules = rules or default_strategy()
    context_ends = [item.close_time for item in higher]
    lower_ends = [bar.close_time for bar in lower or []]
    previous_context = previous_lower = None
    freshness = INTERVALS[CONTEXT_FRAMES[interval]] * 2
    trades = []
    eligible = []
    emitted = set()
    labeled = []
    costs = 2 * (fee_bps + slippage_bps) / 10000
    for i in range(35, len(bars)):
        history = bars[max(0, i - 150):i]
        end = bisect_right(context_ends, history[-1].close_time)
        context = higher[max(0, end - 150):end]
        if len(context) < 35 or bars[i].open <= 0 or bars[i].time != history[-1].close_time:
            continue
        if history[-1].close_time - context[-1].close_time >= freshness:
            continue
        if end != previous_context:
            context_report = analyze(context)
            previous_context = end
        frames = {}
        if rules.require_fvg:
            lower_end = bisect_right(lower_ends, history[-1].close_time)
            if not lower_end or history[-1].close_time - lower_ends[lower_end - 1] >= 600:
                continue
            if lower_end != previous_lower:
                lower_report = analyze(lower[max(0, lower_end - 150):lower_end])
                previous_lower = lower_end
            frames["5m"] = lower_report
        current = analyze(history)
        if not current["indicators"] or not context_report["indicators"]:
            continue
        eligible.append(i)
        signal = opportunity(history, context_report, current, frames, rules=rules, interval=interval)
        price_move = bars[i].close / bars[i].open - 1
        label = (price_move > costs) - (price_move < -costs)
        key = (signal.get("trigger_time"), signal["direction"])
        direction = 0
        if signal["direction"] != "sin señal" and key not in emitted:
            emitted.add(key)
            direction = 1 if signal["direction"] == "posible compra" else -1
            value = direction * price_move - costs
            trades.append((i, value, signal["reward_risk"]))
        labeled.append((i, label, direction))
    overall = metrics(trades, labeled)
    if len(eligible) < 20:
        return {**overall, "out_of_sample": None, "walk_forward": []}
    holdout = eligible[len(eligible) * 3 // 4]
    folds = []
    for start in range(1, 4):
        lower = eligible[len(eligible) * start // 4]
        upper = eligible[len(eligible) * (start + 1) // 4] if start < 3 else len(bars)
        folds.append({"start": bars[lower].time, "end": bars[upper - 1].close_time,
                      **metrics([trade for trade in trades if lower <= trade[0] < upper],
                                [row for row in labeled if lower <= row[0] < upper])})
    return {**overall, "out_of_sample": metrics([trade for trade in trades if trade[0] >= holdout],
                                                       [row for row in labeled if row[0] >= holdout]),
            "walk_forward": folds}


def metrics(trades, labeled):
    correct = sum(label != 0 and label == direction for _, label, direction in labeled)
    positives = sum(label != 0 for _, label, _ in labeled)
    alerts = sum(direction != 0 for _, _, direction in labeled)
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
            "eligible_bars": len(labeled), "without_alert": len(labeled) - alerts,
            "false_positives": alerts - correct,
            "precision": correct / alerts if alerts else None,
            "recall": correct / positives if positives else None,
            "win_rate": sum(value > 0 for value in returns) / len(returns) if returns else None,
            "profit_factor": profits / losses if losses else None,
            "expectancy": sum(returns) / len(returns) if returns else None,
            "maximum_drawdown": drawdown if returns else None,
            "mean_signal_reward_risk": sum(ratios) / len(ratios) if ratios else None}
