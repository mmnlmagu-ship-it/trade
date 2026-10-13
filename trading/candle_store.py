"""SQLite candle store with look-ahead protection."""
import sqlite3
from pathlib import Path
from typing import List, Optional
from trading.types import Candle

_SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    epoch INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (symbol, timeframe, epoch)
);
"""


class CandleStore:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def save_candles(self, candles: List[Candle]) -> int:
        if not candles:
            return 0
        rows = [
            (c.symbol, c.timeframe, c.epoch, c.open, c.high, c.low, c.close, c.volume)
            for c in candles
        ]
        with self._conn:
            self._conn.executemany(
                "INSERT OR REPLACE INTO candles "
                "(symbol, timeframe, epoch, open, high, low, close, volume) "
                "VALUES (?,?,?,?,?,?,?,?)",
                rows,
            )
        return len(rows)

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        *,
        start: Optional[int] = None,
        end: Optional[int] = None,
        as_of: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Candle]:
        """Return CLOSED candles only, never anything after `as_of`.

        If as_of is given, end is clamped to as_of so callers cannot
        accidentally (or deliberately) peek into the future.
        """
        effective_end = end
        if as_of is not None:
            effective_end = as_of if end is None else min(end, as_of)
        q = ("SELECT symbol,timeframe,epoch,open,high,low,close,volume FROM candles "
             "WHERE symbol=? AND timeframe=?")
        args: list = [symbol, timeframe]
        if start is not None:
            q += " AND epoch >= ?"
            args.append(start)
        if effective_end is not None:
            q += " AND epoch <= ?"
            args.append(effective_end)
        q += " ORDER BY epoch ASC"
        if limit is not None:
            q += " LIMIT ?"
            args.append(limit)
        cur = self._conn.execute(q, args)
        return [Candle(*row) for row in cur.fetchall()]

    def get_latest_closed(self, symbol: str, timeframe: str, *, as_of: int) -> Optional[Candle]:
        rows = self.get_candles(symbol, timeframe, as_of=as_of, limit=None)
        return rows[-1] if rows else None

    def close(self) -> None:
        self._conn.close()
