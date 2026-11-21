from backend.alerts import format_alert


def test_alert_contains_market_source_and_execution_disclaimer():
    payload = {
        "direction": "posible compra", "symbol": "BTC/USDT", "timeframe": "15m",
        "price": 100, "observed_at": 900, "evidence": ["BOS"], "risks": ["Sin objetivo"],
        "invalidation": 90, "target": None, "reward_risk": None,
        "chart": "https://example.org/chart",
        "news": [{"title": "Economic release", "url": "https://example.org/news"}],
    }
    message = format_alert(payload)
    for expected in ("POSIBLE COMPRA", "BTC/USDT", "BOS", payload["chart"], payload["news"][0]["url"],
                     "No se ha ejecutado ninguna operación."):
        assert expected in message
