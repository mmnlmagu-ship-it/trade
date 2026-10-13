"""Append-only logger: every decision and every outcome is persisted.

SQLite tables are append-only by convention (no UPDATE/DELETE methods exist).
"""
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    ts INTEGER NOT NULL,
    strategy TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    signal_price REAL NOT NULL,
    units REAL NOT NULL,
    allowed INTEGER NOT NULL,
    veto_reason TEXT NOT NULL DEFAULT '',
    extra_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS outcomes (
    id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    ts INTEGER NOT NULL,
    fill_price REAL NOT NULL,
    pnl REAL NOT NULL,
    balance_after REAL NOT NULL,
    extra_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (decision_id) REFERENCES decisions(id)
);
"""


class DecisionLogger:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def log_decision(
        self,
        *,
        strategy: str,
        symbol: str,
        side: str,
        signal_price: float,
        units: float,
        allowed: bool,
        veto_reason: str = "",
        extra: Optional[Dict[str, Any]] = None,
        ts: Optional[int] = None,
    ) -> str:
        did = uuid.uuid4().hex
        self._conn.execute(
            "INSERT INTO decisions (id,ts,strategy,symbol,side,signal_price,units,allowed,veto_reason,extra_json)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (did, ts or int(time.time()), strategy, symbol, side, signal_price,
             units, int(allowed), veto_reason, json.dumps(extra or {})),
        )
        self._conn.commit()
        return did

    def log_outcome(
        self,
        *,
        decision_id: str,
        fill_price: float,
        pnl: float,
        balance_after: float,
        extra: Optional[Dict[str, Any]] = None,
        ts: Optional[int] = None,
    ) -> str:
        oid = uuid.uuid4().hex
        row = self._conn.execute("SELECT id FROM decisions WHERE id=?", (decision_id,)).fetchone()
        if row is None:
            raise ValueError(f"unknown decision_id {decision_id!r}: outcome must link to a logged decision")
        self._conn.execute(
            "INSERT INTO outcomes (id,decision_id,ts,fill_price,pnl,balance_after,extra_json)"
            " VALUES (?,?,?,?,?,?,?)",
            (oid, decision_id, ts or int(time.time()), fill_price, pnl, balance_after,
             json.dumps(extra or {})),
        )
        self._conn.commit()
        return oid

    def count_decisions(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]

    def count_outcomes(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]

    def close(self) -> None:
        self._conn.close()
