import sys
from pathlib import Path

import pandas as pd

from backtesting.data_loader import BacktestDataLoader
from ml.features import MLFeatureEngineer
from ml.training import ModelTrainer, TargetBuilder
from ml.evaluation import ModelEvaluator
from ml.model_registry import ModelRegistry


def train(
    data_file: str | None = None,
    model_type: str = "xgboost",
    target_type: str = "binary_direction",
    save_model: bool = True,
) -> None:
    loader = BacktestDataLoader()

    if data_file:
        df = loader.load_csv(Path(data_file))
    else:
        print("No data file, using synthetic data (500 candles)")
        df = loader.generate_synthetic(periods=500, start_price=50000.0)

    print(f"Data: {len(df)} candles")
    print(f"Model: {model_type}")
    print(f"Target: {target_type}")
    print("-" * 50)

    feature_eng = MLFeatureEngineer()
    features_df = feature_eng.build_features(df)
    features_df = feature_eng.clean_features(features_df)

    target_builder = TargetBuilder()
    if target_type == "binary_direction":
        target = target_builder.binary_direction(df)
    elif target_type == "forward_return":
        target = target_builder.forward_return(df)
    else:
        target = target_builder.binary_direction(df)

    features_df = features_df.iloc[:len(target)]
    target = target.iloc[:len(features_df)]

    mask = features_df.notna().all(axis=1) & target.notna()
    features_df = features_df[mask]
    target = target[mask]

    if len(features_df) < 50:
        print("Not enough data after cleaning")
        return

    split_idx = int(len(features_df) * 0.8)
    x_train = features_df.iloc[:split_idx]
    y_train = target.iloc[:split_idx]
    x_test = features_df.iloc[split_idx:]
    y_test = target.iloc[split_idx:]

    trainer = ModelTrainer(model_type=model_type)
    model = trainer.train(x_train, y_train)

    evaluator = ModelEvaluator()
    y_pred = model.predict(x_test)
    y_proba = model.predict_proba(x_test)[:, 1] if hasattr(model, "predict_proba") else None

    metrics = evaluator.evaluate(y_test, y_pred, y_proba)

    print(f"Accuracy: {metrics.accuracy:.4f}")
    print(f"Precision: {metrics.precision:.4f}")
    print(f"Recall: {metrics.recall:.4f}")
    if metrics.auc_roc:
        print(f"AUC-ROC: {metrics.auc_roc:.4f}")
    print(f"Train samples: {len(x_train)}")
    print(f"Test samples: {len(x_test)}")

    if save_model:
        registry = ModelRegistry(Path("models"))
        entry = registry.register(
            model=model,
            model_id=f"{model_type}_{target_type}",
            model_type=model_type,
            metrics=metrics.to_dict(),
            feature_names=list(x_train.columns),
            params={"target_type": target_type},
        )
        print(f"Model saved: {entry.model_id}")


def main() -> None:
    data_file = sys.argv[1] if len(sys.argv) > 1 else None
    model_type = sys.argv[2] if len(sys.argv) > 2 else "xgboost"
    train(data_file, model_type)


if __name__ == "__main__":
    main()
