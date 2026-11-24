"""Evaluate the configured crop model on a separate, labeled image directory.

Expected input layout: dataset_root/<exact model label>/*.{jpg,jpeg,png,webp}.
Use only a held-out evaluation set, never the training images.
"""

import argparse
import json
from pathlib import Path

import numpy as np

from app.ml.image_preprocessing import preprocess_image
from app.ml.model_loader import load_class_labels, load_disease_model

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp"}


def evaluate(dataset_root: Path, batch_size: int = 32) -> dict:
    labels = load_class_labels()
    model = load_disease_model()
    if not model.output_shape or model.output_shape[-1] != len(labels):
        raise ValueError("Model output count does not match the configured labels")

    targets: list[int] = []
    predictions: list[int] = []
    class_support: dict[str, int] = {}
    for class_index, label in enumerate(labels):
        class_dir = dataset_root / label
        if not class_dir.is_dir():
            raise ValueError(f"Missing labeled class directory: {label}")
        files = sorted(path for path in class_dir.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED)
        if not files:
            raise ValueError(f"No supported evaluation images found for class: {label}")
        class_support[label] = len(files)
        for start in range(0, len(files), batch_size):
            batch_files = files[start:start + batch_size]
            batch = np.concatenate([preprocess_image(path.read_bytes()) for path in batch_files], axis=0)
            scores = np.asarray(model.predict(batch, verbose=0), dtype=np.float64)
            if scores.ndim != 2 or scores.shape != (len(batch_files), len(labels)) or not np.all(np.isfinite(scores)):
                raise ValueError("Model produced invalid evaluation output")
            predictions.extend(np.argmax(scores, axis=1).astype(int).tolist())
            targets.extend([class_index] * len(batch_files))

    matrix = np.zeros((len(labels), len(labels)), dtype=np.int64)
    np.add.at(matrix, (np.asarray(targets), np.asarray(predictions)), 1)
    per_class = {}
    for index, label in enumerate(labels):
        true_positive = int(matrix[index, index])
        precision_denominator = int(matrix[:, index].sum())
        recall_denominator = int(matrix[index, :].sum())
        precision = true_positive / precision_denominator if precision_denominator else 0.0
        recall = true_positive / recall_denominator if recall_denominator else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "support": recall_denominator,
        }

    total = int(matrix.sum())
    macro_precision = sum(item["precision"] for item in per_class.values()) / len(labels)
    macro_recall = sum(item["recall"] for item in per_class.values()) / len(labels)
    macro_f1 = sum(item["f1_score"] for item in per_class.values()) / len(labels)
    return {
        "dataset": str(dataset_root.resolve()),
        "evaluation_images": total,
        "class_support": class_support,
        "accuracy": float(np.trace(matrix) / total),
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "macro_f1_score": macro_f1,
        "per_class": per_class,
        "confusion_matrix": {"labels": list(labels), "counts": matrix.tolist()},
        "caveat": "Metrics apply only to this held-out dataset and do not establish performance on Kenyan farm images.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_dir", type=Path, help="Held-out class-folder image dataset")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 256:
        parser.error("--batch-size must be between 1 and 256")
    print(json.dumps(evaluate(args.dataset_dir, args.batch_size), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
