from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from ml.evaluation import ModelEvaluator
from ml.features import MLFeatureEngineer, get_all_feature_names
from ml.model_registry import ModelRegistry
from ml.training import ModelTrainer, TargetBuilder
from scripts.build_ml_dataset import build_dataset


def _load_ml_candidates(data_dir: Path) -> list[dict]:
    path = data_dir / "ml_candidates.jsonl"
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _match_signals_to_outcomes(
    db_path: Path, horizon_hours: int = 6,
) -> pd.DataFrame:
    tmp_out = db_path.parent / "_tmp_ml_dataset.csv"
    count = build_dataset(db_path, tmp_out, horizon_hours)
    if count == 0:
        return pd.DataFrame()
    df = pd.read_csv(tmp_out)
    tmp_out.unlink(missing_ok=True)
    return df


def _features_from_candidates(
    candidates: list[dict], dataset: pd.DataFrame,
) -> pd.DataFrame:
    lookup: dict[tuple[str, str], dict[str, float]] = {}
    for c in candidates:
        ts = c.get("timestamp", "")
        symbol = c.get("symbol", "")
        ml_feats = c.get("ml_features")
        if ml_feats and isinstance(ml_feats, dict):
            lookup[(ts[:19], symbol)] = ml_feats

    feature_names = get_all_feature_names()
    rows = []
    for _, row in dataset.iterrows():
        sig_ts = str(row.get("signal_ts", ""))[:19]
        symbol = str(row.get("symbol", ""))
        feats = lookup.get((sig_ts, symbol))
        if feats:
            rows.append(feats)
        else:
            rows.append({f: np.nan for f in feature_names})

    return pd.DataFrame(rows, columns=feature_names)


def enrich_and_train(
    db_path: Path,
    data_dir: Path,
    model_dir: Path,
    min_samples: int = 100,
    model_type: str = "xgboost",
) -> dict:
    print(f"Loading journal from {db_path}")
    dataset = _match_signals_to_outcomes(db_path)
    if dataset.empty:
        print("No matched signal/trade pairs found")
        return {"status": "no_data", "samples": 0}

    print(f"Matched {len(dataset)} signal-trade pairs")
    candidates = _load_ml_candidates(data_dir)
    print(f"Loaded {len(candidates)} ML candidates from JSONL")

    features_df = _features_from_candidates(candidates, dataset)

    has_features = features_df.notna().any(axis=1)
    print(f"Signals with stored ML features: {has_features.sum()}/{len(features_df)}")

    features_df = features_df.replace([np.inf, -np.inf], np.nan)
    features_df = features_df.ffill().bfill().fillna(0)

    labels = dataset["label_win"].astype(int)

    mask = features_df.notna().all(axis=1) & labels.notna()
    features_df = features_df[mask].reset_index(drop=True)
    labels = labels[mask].reset_index(drop=True)

    if len(features_df) < min_samples:
        print(f"Not enough labeled samples: {len(features_df)} < {min_samples}")
        return {"status": "insufficient_data", "samples": len(features_df)}

    print(f"Training on {len(features_df)} samples with {len(features_df.columns)} features")

    trainer = ModelTrainer(model_type=model_type)
    cv_results = trainer.walk_forward_cv(features_df, labels, n_splits=5)
    avg_cv_acc = np.mean([r["accuracy"] for r in cv_results])
    print(f"Walk-forward CV accuracy (5 folds): {avg_cv_acc:.4f}")
    for i, r in enumerate(cv_results):
        print(f"  Fold {i + 1}: accuracy={r['accuracy']:.4f}, log_loss={r['log_loss']:.4f}, n={r['n_test']}")

    split_idx = int(len(features_df) * 0.8)
    x_train = features_df.iloc[:split_idx]
    y_train = labels.iloc[:split_idx]
    x_test = features_df.iloc[split_idx:]
    y_test = labels.iloc[split_idx:]

    trainer_final = ModelTrainer(model_type=model_type)
    model = trainer_final.train(x_train, y_train)

    evaluator = ModelEvaluator()
    y_pred = model.predict(x_test)
    y_proba = model.predict_proba(x_test) if hasattr(model, "predict_proba") else None
    metrics = evaluator.evaluate(y_test, y_pred, y_proba)

    print(f"\nTest Results ({len(x_test)} samples):")
    print(f"  Accuracy:  {metrics.accuracy:.4f}")
    print(f"  Precision: {metrics.precision:.4f}")
    print(f"  Recall:    {metrics.recall:.4f}")
    if metrics.auc_roc:
        print(f"  AUC-ROC:   {metrics.auc_roc:.4f}")

    result = {
        "status": "trained",
        "samples": len(features_df),
        "cv_accuracy": avg_cv_acc,
        "test_accuracy": metrics.accuracy,
        "test_precision": metrics.precision,
        "test_recall": metrics.recall,
        "test_auc": metrics.auc_roc,
    }

    if metrics.accuracy > 0.52:
        registry = ModelRegistry(model_dir)
        entry = registry.register(
            model=model,
            model_id="direction_classifier",
            model_type=model_type,
            metrics=metrics.to_dict(),
            feature_names=list(features_df.columns),
            params={
                "min_samples": min_samples,
                "train_samples": len(x_train),
                "test_samples": len(x_test),
                "cv_accuracy": avg_cv_acc,
            },
        )
        print(f"\nModel saved: {entry.model_id} (accuracy={metrics.accuracy:.4f} > 0.52)")
        result["model_id"] = entry.model_id
    else:
        print(f"\nModel NOT saved: accuracy {metrics.accuracy:.4f} <= 0.52")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich signals with features and train ML model")
    parser.add_argument("--db", default="journal.db", help="Path to journal.db")
    parser.add_argument("--data-dir", default="data", help="Data directory with ml_candidates.jsonl")
    parser.add_argument("--model-dir", default="models", help="Directory to save trained models")
    parser.add_argument("--min-samples", type=int, default=100, help="Minimum labeled samples to train")
    parser.add_argument("--model-type", default="xgboost", choices=["xgboost", "lightgbm"])
    args = parser.parse_args()

    enrich_and_train(
        db_path=Path(args.db),
        data_dir=Path(args.data_dir),
        model_dir=Path(args.model_dir),
        min_samples=args.min_samples,
        model_type=args.model_type,
    )


if __name__ == "__main__":
    main()
