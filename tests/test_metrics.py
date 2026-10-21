import pytest

from core.metrics import accuracy, confusion, percentile, precision_recall_f1


def test_confusion_and_prf():
    gt = ["defect", "defect", "good", "good", "defect", "good"]
    pr = ["defect", "good", "defect", "good", "unknown", "unknown"]
    c = confusion(gt, pr)
    assert (c["tp"], c["fn"], c["fp"], c["tn"], c["unknown"]) == (1, 2, 1, 2, 2)
    p, r, f1 = precision_recall_f1(c)
    assert p == pytest.approx(0.5)
    assert r == pytest.approx(1 / 3)
    assert f1 == pytest.approx(0.4)
    assert accuracy(gt, pr) == pytest.approx(2 / 6)


def test_zero_denominators_are_none():
    c = confusion(["good", "good"], ["good", "good"])
    assert precision_recall_f1(c) == (None, None, None)
    assert accuracy([], []) is None


def test_percentile_matches_linear_interpolation():
    assert percentile([1, 2, 3, 4], 50) == pytest.approx(2.5)
    assert percentile([5], 95) == 5
    assert percentile([], 95) is None
    assert percentile(range(1, 101), 95) == pytest.approx(95.05)


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        confusion(["good"], [])
