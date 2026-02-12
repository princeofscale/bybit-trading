import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.enrich_and_train import (
    _features_from_candidates,
    _load_ml_candidates,
    _match_signals_to_outcomes,
)


def _create_journal_db(db_path: Path, n_signals: int = 5, n_trades: int = 5) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS signals (
            timestamp TEXT, symbol TEXT, direction TEXT,
            confidence REAL, strategy_name TEXT,
            entry_price TEXT, stop_loss TEXT, take_profit TEXT,
            approved INTEGER, rejection_reason TEXT, session_id TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS trades (
            timestamp TEXT, symbol TEXT, side TEXT,
            entry_price TEXT, exit_price TEXT, quantity TEXT,
            realized_pnl TEXT, pnl_pct TEXT,
            strategy_name TEXT, hold_duration_ms INTEGER, session_id TEXT
        )"""
    )
    base_ts = pd.Timestamp("2026-01-01 10:00:00")
    for i in range(n_signals):
        ts = (base_ts + pd.Timedelta(minutes=i * 30)).isoformat()
        conn.execute(
            "INSERT INTO signals VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ts, "BTC/USDT:USDT", "long", 0.7, "ema_crossover", "50000", "49500", "51000", 1, "", "s1"),
        )
    for i in range(n_trades):
        ts = (base_ts + pd.Timedelta(minutes=i * 30 + 10)).isoformat()
        pnl = 10.0 if i % 2 == 0 else -5.0
        conn.execute(
            "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ts, "BTC/USDT:USDT", "long", "50000", "50100", "0.001", str(pnl), "0.02", "ema_crossover", 600000, "s1"),
        )
    conn.commit()
    conn.close()


def test_match_signals_to_outcomes(tmp_path: Path) -> None:
    db = tmp_path / "journal.db"
    _create_journal_db(db)
    dataset = _match_signals_to_outcomes(db, horizon_hours=6)
    assert not dataset.empty
    assert "label_win" in dataset.columns
    assert "signal_ts" in dataset.columns


def test_match_signals_empty_db(tmp_path: Path) -> None:
    db = tmp_path / "journal.db"
    _create_journal_db(db, n_signals=0, n_trades=0)
    dataset = _match_signals_to_outcomes(db, horizon_hours=6)
    assert dataset.empty


def test_load_ml_candidates(tmp_path: Path) -> None:
    path = tmp_path / "ml_candidates.jsonl"
    records = [
        {"timestamp": "2026-01-01T10:00:00", "symbol": "BTC/USDT:USDT", "ml_features": {"rsi_14": 55.0}},
        {"timestamp": "2026-01-01T10:30:00", "symbol": "BTC/USDT:USDT", "ml_features": {"rsi_14": 60.0}},
    ]
    with path.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    loaded = _load_ml_candidates(tmp_path)
    assert len(loaded) == 2
    assert loaded[0]["ml_features"]["rsi_14"] == 55.0


def test_load_ml_candidates_missing_file(tmp_path: Path) -> None:
    loaded = _load_ml_candidates(tmp_path)
    assert loaded == []


def test_features_from_candidates() -> None:
    candidates = [
        {
            "timestamp": "2026-01-01T10:00:00+00:00",
            "symbol": "BTC/USDT:USDT",
            "ml_features": {"rsi_14": 55.0, "ema_9": 50100.0},
        },
    ]
    dataset = pd.DataFrame([{
        "signal_ts": "2026-01-01T10:00:00+00:00",
        "symbol": "BTC/USDT:USDT",
        "label_win": 1,
    }])
    features = _features_from_candidates(candidates, dataset)
    assert len(features) == 1
    assert features.iloc[0]["rsi_14"] == 55.0
