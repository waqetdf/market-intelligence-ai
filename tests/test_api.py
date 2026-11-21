from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from backend import app as application


def test_multisource_registration_and_mt5_import(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(application, "engine", create_engine(f"sqlite:///{tmp_path / 'market.db'}"))
    monkeypatch.setattr(application, "data", tmp_path)
    monkeypatch.setenv("MARKET_PASSWORD", "test-password")
    monkeypatch.setenv("MARKET_REQUIRE_AUTH", "1")
    path = tmp_path / "mt5" / "scan_20260101_000000_UTC"
    path.mkdir(parents=True)
    (path / "GOLD_M15.csv").write_text(
        "time_utc,open,high,low,close,tick_volume\n2020-01-02T12:00:00+00:00,10,12,9,11,25\n",
        encoding="utf-8",
    )
    with TestClient(application.app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/assets").status_code == 401
        client.auth = ("admin", "test-password")
        gold = {"symbol": "XAUUSD", "source": "mt5-csv", "ticker": "GOLD"}
        crypto = {"symbol": "BTC/USDT", "source": "binance", "ticker": "BTCUSDT"}
        assert client.post("/api/assets", json=gold).status_code == 201
        assert client.post("/api/assets", json=gold).status_code == 409
        assert client.post("/api/assets", json=crypto).status_code == 201
        payload = client.get("/api/candles", params={"symbol": "XAUUSD", "interval": "15m"}).json()
        assert payload["source"] == "mt5-csv"
        assert payload["bars"][0]["close"] == 11
        assert payload["bars"][0]["close_time"] - payload["bars"][0]["time"] == 900
        assert client.get("/api/candles", params={"symbol": "XAUUSD", "interval": "4h"}).status_code == 502


def test_scan_records_closed_decision_once(tmp_path, monkeypatch):
    import asyncio

    from backend.market import Asset, Candle, INTERVALS

    engine = create_engine(f"sqlite:///{tmp_path / 'scan.db'}")
    monkeypatch.setattr(application, "engine", engine)
    application.metadata.create_all(engine)
    calls = []

    async def candles(asset, interval):
        calls.append(interval)
        closing = 1001 if interval == "4h" else 1000
        return [Candle(time=1, close_time=closing, open=10, high=11, low=9, close=10, volume=5)]

    monkeypatch.setattr(application, "candles", candles)
    monkeypatch.setattr(application, "time", lambda: 1000)
    asset = Asset(symbol="BTC/USDT", source="binance", ticker="BTCUSDT")
    asyncio.run(application.scan_asset(asset))
    asyncio.run(application.scan_asset(asset))
    assert set(calls) == set(INTERVALS)
    decision, = application.history()
    assert decision["direction"] == "sin señal"
    assert "4h" not in decision["trends"]
    assert application.list_alerts() == []


def test_admin_controls_only_preconfigured_integrations(tmp_path, monkeypatch):
    monkeypatch.setattr(application, "engine", create_engine(f"sqlite:///{tmp_path / 'settings.db'}"))
    monkeypatch.setattr(application, "data", tmp_path)
    monkeypatch.setenv("MARKET_PASSWORD", "test-password")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.org/private-webhook")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with TestClient(application.app) as client:
        assert client.get("/api/settings").status_code == 401
        client.auth = ("admin", "test-password")
        report = client.get("/api/settings")
        assert report.json()["integrations"]["discord"]
        assert "private-webhook" not in report.text
        payload = {"discord": False, "ai": False, "telegram": True}
        assert client.put("/api/settings/integrations", json=payload).status_code == 422
        payload["telegram"] = False
        assert client.put("/api/settings/integrations", json=payload).status_code == 200
        assert not client.get("/api/settings").json()["integrations"]["discord"]
