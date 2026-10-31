"""
AI Agent Evaluation
--------------------
Runs the AI agent against a labeled CSV of reviews and reports Accuracy,
Precision, Recall, F1 Score, and a confusion matrix — real metrics
computed from actual predictions, never fabricated.

This does NOT train anything — it only measures how well the agent's
reasoning-based judgments align with known ground-truth labels, so the
prompt can be refined based on real mistakes.

Usage:
    python -m src.agent.evaluate --file data/sample_reviews.csv
    python -m src.agent.evaluate --file data/kaggle_fake_reviews.csv --limit 200
"""

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from agent.classifier import classify_review, AgentResponseError

MIN_ROWS_FOR_RELIABLE_METRICS = 30


def load_reviews(csv_path: str, limit: int | None = None) -> list[dict]:
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return rows[:limit] if limit else rows


def compute_metrics(true_labels: list[str], predicted_labels: list[str], positive_label: str = "Fake") -> dict:
    """
    Computes Accuracy, Precision, Recall, F1 (treating `positive_label` as
    the positive class) and a 2x2 confusion matrix, from real prediction
    pairs — no fabricated numbers.
    """
    assert len(true_labels) == len(predicted_labels)
    n = len(true_labels)

    tp = sum(1 for t, p in zip(true_labels, predicted_labels) if t == positive_label and p == positive_label)
    tn = sum(1 for t, p in zip(true_labels, predicted_labels) if t != positive_label and p != positive_label)
    fp = sum(1 for t, p in zip(true_labels, predicted_labels) if t != positive_label and p == positive_label)
    fn = sum(1 for t, p in zip(true_labels, predicted_labels) if t == positive_label and p != positive_label)

    accuracy = (tp + tn) / n if n else 0
    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) else 0

    return {
        "n": n,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "confusion_matrix": {
            "true_positive": tp,   # predicted Fake, actually Fake
            "false_positive": fp,  # predicted Fake, actually Genuine
            "true_negative": tn,   # predicted Genuine, actually Genuine
            "false_negative": fn,  # predicted Genuine, actually Fake
        },
    }


def print_confusion_matrix(cm: dict, positive_label: str = "Fake", negative_label: str = "Genuine") -> None:
    print("\nConfusion Matrix (rows = actual, columns = predicted):")
    print(f"{'':>18}{positive_label:>12}{negative_label:>12}")
    print(f"{'actual ' + positive_label:>18}{cm['true_positive']:>12}{cm['false_negative']:>12}")
    print(f"{'actual ' + negative_label:>18}{cm['false_positive']:>12}{cm['true_negative']:>12}")


def evaluate(csv_path: str, limit: int | None = None, delay: float = 0.0) -> None:
    rows = load_reviews(csv_path, limit)
    total = len(rows)

    true_labels = []
    predicted_labels = []
    failed_parses = []
    misclassified = []

    print(f"Evaluating AI agent on {total} labeled reviews...\n")

    for i, row in enumerate(rows, start=1):
        review_text = row["review_text"]
        rating = int(row["rating"]) if row.get("rating") else None
        true_label = row["true_label"].strip()

        try:
            result = classify_review(review_text, rating)
            predicted = result["label"].strip()
        except AgentResponseError as e:
            failed_parses.append({"index": i, "review": review_text, "error": str(e)})
            print(f"[{i}/{total}] VALIDATION ERROR — {e}")
            continue
        except Exception as e:
            failed_parses.append({"index": i, "review": review_text, "error": str(e)})
            print(f"[{i}/{total}] API ERROR — {e}")
            continue

        true_labels.append(true_label)
        predicted_labels.append(predicted)

        status = "OK" if predicted == true_label else "MISS"
        color = "\033[91m" if predicted == "Fake" else "\033[92m"
        reset = "\033[0m"
        line_mark = f"{color}━ [False/Fake]{reset}" if predicted == "Fake" else f"{color}━ [True/Genuine]{reset}"
        print(f"[{i:02d}/{total:02d}] {status:4s} {line_mark:22s} true={true_label:8s} pred={predicted:8s} "
              f"level={result['confidence_level']:6s} conf={result['confidence']}%")

        if predicted != true_label:
            misclassified.append({
                "index": i, "review": review_text, "true": true_label,
                "predicted": predicted, "reasoning": result["reasoning"],
            })

        if delay:
            time.sleep(delay)

    evaluated = len(true_labels)

    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"Total reviews:        {total}")
    print(f"Successfully parsed:  {evaluated}")
    print(f"Failed to parse:      {len(failed_parses)}")

    if evaluated == 0:
        print("\nNo predictions succeeded — cannot compute metrics.")
        return

    metrics = compute_metrics(true_labels, predicted_labels, positive_label="Fake")

    print(f"\nAccuracy:   {metrics['accuracy'] * 100:.2f}%")
    print(f"Precision:  {metrics['precision'] * 100:.2f}%  (of predicted Fake, how many were actually Fake)")
    print(f"Recall:     {metrics['recall'] * 100:.2f}%  (of actual Fake, how many were caught)")
    print(f"F1 Score:   {metrics['f1'] * 100:.2f}%")

    print_confusion_matrix(metrics["confusion_matrix"])

    if evaluated < MIN_ROWS_FOR_RELIABLE_METRICS:
        print(
            f"\n⚠️  LIMITATION: only {evaluated} labeled rows were evaluated. "
            f"Metrics from fewer than {MIN_ROWS_FOR_RELIABLE_METRICS} examples are "
            "not statistically reliable — treat these numbers as a rough smoke "
            "test, not a real performance claim. Re-run against a larger labeled "
            "dataset (e.g. the Kaggle Fake Reviews Dataset) for a meaningful result."
        )

    if misclassified:
        print(f"\n{len(misclassified)} misclassified review(s) — review these to refine the prompt:")
        for m in misclassified:
            print(f"  #{m['index']} true={m['true']} pred={m['predicted']} :: {m['reasoning']}")

    if failed_parses:
        print(f"\n{len(failed_parses)} response(s) failed validation — check agent output formatting:")
        for f in failed_parses:
            print(f"  #{f['index']}: {f['error']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate the AI agent against a labeled review dataset.")
    parser.add_argument("--file", required=True, help="Path to a CSV with columns: review_text, rating, true_label")
    parser.add_argument("--limit", type=int, default=None, help="Optional cap on number of rows to evaluate")
    parser.add_argument("--delay", type=float, default=0.0, help="Seconds to wait between API calls (rate-limit safety)")
    args = parser.parse_args()

    evaluate(args.file, args.limit, args.delay)
