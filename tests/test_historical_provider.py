"""Opt-in contract test against Binance's public, read-only historical API."""

import asyncio
from datetime import datetime, timezone
import os

import pytest

from backend.market import Asset, get_candles
from backend.technical import analyze


@pytest.mark.skipif(os.getenv("MARKET_LIVE_TEST") != "1", reason="requires real internet access")
def test_binance_history_reproduces_confirmed_events(tmp_path):
    cutoff = int(datetime(2025, 1, 20, tzinfo=timezone.utc).timestamp())
    asset = Asset(symbol="BTC/USDT", source="binance", ticker="BTCUSDT")
    bars = asyncio.run(get_candles(asset, "15m", tmp_path, cutoff, limit=750))
    assert len(bars) == 750
    assert all(bar.close_time <= cutoff for bar in bars)
    full = analyze(bars)
    assert {"Swing High", "Swing Low", "BOS", "CHoCH", "FVG", "IFVG",
            "Order Block", "Liquidity Sweep"} <= {event["kind"] for event in full["events"]}
    for size in (150, 300, 450, 600):
        as_of = bars[size - 1].close_time
        assert analyze(bars[:size])["events"] == [
            event for event in full["events"] if event["confirmed_at"] <= as_of
        ]
