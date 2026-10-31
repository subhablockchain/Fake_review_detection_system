"""
Tests for src/agent/evaluate.py's metric computation — pure functions,
no API calls needed, so these run instantly.

Run with: pytest tests/test_evaluate.py -v
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.agent.evaluate import compute_metrics


def test_perfect_predictions():
    true = ["Fake", "Fake", "Genuine", "Genuine"]
    pred = ["Fake", "Fake", "Genuine", "Genuine"]
    m = compute_metrics(true, pred)
    assert m["accuracy"] == 1.0
    assert m["precision"] == 1.0
    assert m["recall"] == 1.0
    assert m["f1"] == 1.0
    assert m["confusion_matrix"]["true_positive"] == 2
    assert m["confusion_matrix"]["true_negative"] == 2
    assert m["confusion_matrix"]["false_positive"] == 0
    assert m["confusion_matrix"]["false_negative"] == 0


def test_all_wrong_predictions():
    true = ["Fake", "Genuine"]
    pred = ["Genuine", "Fake"]
    m = compute_metrics(true, pred)
    assert m["accuracy"] == 0.0
    assert m["precision"] == 0.0
    assert m["recall"] == 0.0
    assert m["f1"] == 0.0


def test_mixed_predictions_known_values():
    # 2 actual Fake (1 caught, 1 missed), 2 actual Genuine (1 correctly
    # kept, 1 wrongly flagged as Fake)
    true = ["Fake", "Fake", "Genuine", "Genuine"]
    pred = ["Fake", "Genuine", "Genuine", "Fake"]
    m = compute_metrics(true, pred)
    cm = m["confusion_matrix"]
    assert cm["true_positive"] == 1   # Fake correctly caught
    assert cm["false_negative"] == 1  # Fake missed
    assert cm["false_positive"] == 1  # Genuine wrongly flagged
    assert cm["true_negative"] == 1   # Genuine correctly kept
    assert m["accuracy"] == 0.5
    assert m["precision"] == 0.5  # 1 true positive / 2 predicted positive
    assert m["recall"] == 0.5     # 1 true positive / 2 actual positive
    assert round(m["f1"], 4) == 0.5


def test_empty_input_does_not_crash():
    m = compute_metrics([], [])
    assert m["n"] == 0
    assert m["accuracy"] == 0
    assert m["precision"] == 0
    assert m["recall"] == 0
    assert m["f1"] == 0


def test_no_predicted_positives_gives_zero_precision_not_error():
    # Agent never predicts "Fake" at all -> precision denominator is 0;
    # must return 0, not raise a ZeroDivisionError.
    true = ["Fake", "Genuine"]
    pred = ["Genuine", "Genuine"]
    m = compute_metrics(true, pred)
    assert m["precision"] == 0
    assert m["recall"] == 0  # no Fake caught either
