from datetime import datetime, timezone
import sqlite3

from backend.calendar import nearby_releases, parse_schedule
from backend.forward import evaluate_alert
from backend.local_backup import backup_database
from backend.market import Candle
from backend.signals import Strategy, assess_quality, strategy_signature


def test_calendar_preserves_official_time_and_filters_nonmajor_releases():
    schedule = """BEGIN:VEVENT
DTSTART;TZID=US-Eastern:20261120T083000
SUMMARY:Employment Situation
END:VEVENT
BEGIN:VEVENT
DTSTART:20261101T120000Z
SUMMARY:Local bulletin
END:VEVENT
"""
    event, = parse_schedule(schedule)
    expected = int(datetime(2026, 11, 20, 13, 30, tzinfo=timezone.utc).timestamp())
    assert event["starts_at"] == expected
    assert nearby_releases([event], expected + 60, 1) == [event]
    assert nearby_releases([event], expected + 61, 1) == []


def test_backup_preserves_committed_data_and_reuses_daily_copy(tmp_path):
    with sqlite3.connect(tmp_path / "market.db") as db:
        db.execute("CREATE TABLE test (val)")
        db.execute("INSERT INTO test VALUES (12)")
    first = backup_database(tmp_path, automatic=True)
    assert backup_database(tmp_path, automatic=True) == first
    with sqlite3.connect(first) as copy:
        assert copy.execute("SELECT val FROM test").fetchone() == (12,)


def test_quality_requires_prior_matching_holdout_and_minimum_sample():
    rule = Strategy(window=5, volume_min=1)
    signature = strategy_signature(rule)
    historical = {"bar_end": 50, "created_at": 60, "strategy": signature, "id": "history",
                  "out_of_sample": {"count": 100, "precision": .7, "expectancy": .01}}
    assert assess_quality(historical, 59, signature)["status"] == "sin calibrar"
    assert assess_quality(historical, 61, signature)["status"] == "respaldo histórico preliminar"
    historical["out_of_sample"]["count"] = 12
    assert assess_quality(historical, 61, signature)["status"] == "muestra insuficiente"
    assert assess_quality(historical, 61, strategy_signature(Strategy(window=5, volume_min=2)))["status"] == "sin calibrar"


def test_forward_only_consumes_the_immediately_following_closed_bar():
    alert = {"observed_at": 100, "symbol": "BTC/USDT", "timeframe": "15m", "direction": "posible venta"}
    bar = Candle(time=100, close_time=1000, open=100, low=95, high=100, close=95, volume=10)
    report = evaluate_alert(alert, bar, fee_bps=0, slippage_bps=0)
    assert round(report["net_return"], 4) == .05
    assert report["mode"] == "simulación de alerta en vivo"
    assert evaluate_alert(dict(alert, observed_at=99), bar) is None
