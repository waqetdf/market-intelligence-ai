from backend.market import Candle
from backend.signals import replay


def test_replay_preserves_chronology_of_validation_windows():
    def bar(i):
        return Candle(time=i * 60, close_time=(i + 1) * 60, open=10,
                      low=9, high=11, close=10, volume=10)

    result = replay([bar(i) for i in range(100)], [bar(i) for i in range(100)])
    windows = result["walk_forward"]
    assert len(windows) == 3
    assert all(left["end"] <= right["start"] for left, right in zip(windows, windows[1:]))
    assert result["out_of_sample"]["count"] == windows[-1]["count"] == 0
