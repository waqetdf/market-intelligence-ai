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


def test_precision_recall_use_all_evaluable_bars():
    from backend.signals import metrics

    report = metrics([(1, .02, None), (2, -.02, None)],
                     [(1, 1, 1), (2, 0, -1), (3, -1, 0), (4, 0, 0)])
    assert report["precision"] == report["recall"] == .5
    assert report["false_positives"] == 1
    assert report["without_alert"] == 2
