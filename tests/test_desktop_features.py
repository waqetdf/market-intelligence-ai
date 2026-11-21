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


def test_local_secrets_are_not_reused_for_a_changed_model_endpoint(tmp_path, monkeypatch):
    from backend.local_integrations import read_local_integrations, save_local_integrations

    for key in ("MARKET_AI_PROVIDER", "MARKET_AI_URL", "MARKET_AI_MODEL", "MARKET_AI_TOKEN"):
        monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv(key, "")
    save_local_integrations(tmp_path, "ai", ["openai-compatible", "https://example.org", "m", "secret"], False)
    assert read_local_integrations(tmp_path)["MARKET_AI_TOKEN"] == "secret"
    save_local_integrations(tmp_path, "ai", ["openai-compatible", "https://example.com", "m", ""], False)
    assert read_local_integrations(tmp_path)["MARKET_AI_TOKEN"] == ""


def test_linux_autostart_is_opt_in_and_quotes_paths(tmp_path, monkeypatch):
    from backend import desktop_startup

    monkeypatch.setattr(desktop_startup.sys, "platform", "linux")
    entrypoint = tmp_path / "app folder" / "100% desktop.py"
    assert not desktop_startup.startup_enabled(tmp_path)
    desktop_startup.set_startup(tmp_path, entrypoint, True)
    command = desktop_startup.linux_startup_path(tmp_path).read_text()
    assert '100%% desktop.py" "--background"' in command
    assert desktop_startup.startup_enabled(tmp_path)
    desktop_startup.set_startup(tmp_path, entrypoint, False)
    assert not desktop_startup.startup_enabled(tmp_path)
