from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd


def build_dataset(db_path: Path, output_path: Path, horizon_hours: int) -> int:
    conn = sqlite3.connect(db_path)
    try:
        signals = pd.read_sql_query(
            """
            SELECT timestamp, symbol, direction, confidence, strategy_name, approved, rejection_reason
            FROM signals
            WHERE approved = 1
            ORDER BY timestamp ASC
            """,
            conn,
            parse_dates=["timestamp"],
        )
        trades = pd.read_sql_query(
            """
            SELECT timestamp, symbol, realized_pnl, pnl_pct, strategy_name
            FROM trades
            ORDER BY timestamp ASC
            """,
            conn,
            parse_dates=["timestamp"],
        )
    finally:
        conn.close()

    if signals.empty:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame().to_csv(output_path, index=False)
        return 0

    rows: list[dict[str, object]] = []
    horizon = pd.Timedelta(hours=horizon_hours)
    for signal in signals.itertuples(index=False):
        cutoff = signal.timestamp + horizon
        candidates = trades[
            (trades["symbol"] == signal.symbol)
            & (trades["timestamp"] >= signal.timestamp)
            & (trades["timestamp"] <= cutoff)
        ]
        if candidates.empty:
            continue
        trade = candidates.iloc[0]
        rows.append(
            {
                "signal_ts": signal.timestamp.isoformat(),
                "symbol": signal.symbol,
                "direction": signal.direction,
                "confidence": signal.confidence,
                "strategy_name": signal.strategy_name,
                "trade_ts": trade["timestamp"].isoformat(),
                "realized_pnl": float(trade["realized_pnl"]),
                "pnl_pct": float(trade["pnl_pct"]),
                "label_win": int(float(trade["realized_pnl"]) > 0),
            }
        )

    dataset = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(output_path, index=False)
    return len(dataset)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build offline ML dataset from journal.db")
    parser.add_argument("--db", default="journal.db", help="Path to journal SQLite database")
    parser.add_argument(
        "--out",
        default="data/ml_train_dataset.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--horizon-hours",
        type=int,
        default=6,
        help="Max delay between signal and matched trade",
    )
    args = parser.parse_args()

    count = build_dataset(Path(args.db), Path(args.out), args.horizon_hours)
    print(f"dataset_rows={count} output={args.out}")


if __name__ == "__main__":
    main()
