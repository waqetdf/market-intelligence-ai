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
