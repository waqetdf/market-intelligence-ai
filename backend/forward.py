"""Paper evaluation of alerts generated during live monitoring."""

DEFAULT_FEE_BPS = 10
DEFAULT_SLIPPAGE_BPS = 5


def evaluate_alert(alert, bar, fee_bps=DEFAULT_FEE_BPS, slippage_bps=DEFAULT_SLIPPAGE_BPS):
    observed = alert["observed_at"]
    direction = {"posible compra": 1, "posible venta": -1}.get(alert["direction"])
    if not direction or bar.time != observed or bar.open <= 0:
        return None
    cost = 2 * (fee_bps + slippage_bps) / 10000
    return {"symbol": alert["symbol"], "timeframe": alert["timeframe"], "direction": alert["direction"],
            "observed_at": observed, "resolved_at": bar.close_time, "entry": bar.open, "exit": bar.close,
            "net_return": direction * (bar.close / bar.open - 1) - cost,
            "fee_bps": fee_bps, "slippage_bps": slippage_bps, "mode": "simulación de alerta en vivo"}
