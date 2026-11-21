from backend.market import Candle, closed_candles
from backend.technical import analyze


def candle(i, low, high):
    return Candle(time=i, close_time=i + 1, open=low, low=low,
                  high=high, close=high, volume=10)


def test_closed_candles_are_ordered_and_deduplicated():
    first, second, forming = candle(1, 2, 3), candle(2, 3, 4), candle(3, 4, 5)
    assert closed_candles([forming, second, first, second], 3, 10) == [first, second]


def test_confirmed_swing_is_causal():
    bars = [candle(i, value - 1, value) for i, value in enumerate([3, 4, 8, 4, 3, 10])]
    assert not any(e["kind"] == "Swing High" for e in analyze(bars[:4])["events"])
    events = analyze(bars)["events"]
    assert next(e for e in events if e["kind"] == "Swing High")["time"] == 4
    assert next(e for e in events if e["kind"] == "BOS")["time"] == 5


def test_order_block_updates_only_after_breakout():
    bars = [candle(i, value - 1, value) for i, value in enumerate([3, 4, 8, 4, 3, 10])]
    bars[4] = bars[4].model_copy(update={"open": 3, "close": 2})
    first = analyze(bars)
    assert first["blocks"][0]["state"] == "abierto"
    assert first["blocks"][0]["origin"] == 4
    touched = analyze([*bars, candle(6, 2.5, 4)])
    assert touched["blocks"][0]["state"] == "mitigado"
    assert touched["events"][-1]["time"] == 6
    invalid = analyze([*bars, candle(6, 1, 1.5)])
    assert invalid["blocks"][0]["state"] == "invalidado"
    assert any(event["kind"] == "Breaker Block" for event in invalid["events"])
