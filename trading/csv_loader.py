"""CSV data source (used because MT5 is NOT reachable from here).

MT5 desktop (Windows) is required for MetaTrader5-python + terminal pipe;
this Linux VM has neither, so daily candles arrive as CSV exports:
MT5 chart -> D1 -> Ctrl+S, or File -> Save as. One file per symbol.

Accepted formats per file:
  1. MT5 export: DATE,TIME,OPEN,HIGH,LOW,CLOSE,TICKVOL,VOL,SPREAD
     dates as YYYY.MM.DD, tabs or commas.
  2. Generic: date,open,high,low,close[,volume] with YYYY-MM-DD or YYYY.MM.DD.
Header row optional; autodetected.
"""
import csv
import datetime as dt
from pathlib import Path
from typing import Dict, List, Tuple
from trading.mt5_symbols import CANONICAL_SYMBOLS, resolve_symbol
from trading.types import Candle

TIMEFRAME = "D1"


def _parse_date(s: str) -> dt.date:
    s = s.strip()
    for fmt in ("%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unparseable date {s!r}")


def _epoch_of_day(d: dt.date) -> int:
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp())


def _is_header(row: List[str]) -> bool:
    joined = ",".join(row).upper()
    return any(k in joined for k in ("DATE", "OPEN", "CLOSE", "<DATE"))


def load_daily_csv(path: str | Path, symbol: str, timeframe: str = TIMEFRAME) -> List[Candle]:
    """Load one daily CSV into sorted Candle list. Raises on garbage."""
    canon = resolve_symbol(symbol) or symbol.strip().upper()
    rows: List[Candle] = []
    errors: List[str] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        sample = f.read(4096)
        f.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;") if sample.strip() else csv.excel
        reader = csv.reader(f, dialect)
        for ln, row in enumerate(reader, 1):
            if not row or all(not c.strip() for c in row):
                continue
            if _is_header(row):
                continue
            try:
                cells = [c.strip().strip("<>") for c in row]
                d = _parse_date(cells[0])
                # MT5 export has TIME in cells[1]; generic may not
                off = 0
                if len(cells) >= 6 and ":" in cells[1]:
                    off = 1  # skip TIME col
                o, h, l, c = (float(cells[1 + off]), float(cells[2 + off]),
                              float(cells[3 + off]), float(cells[4 + off]))
                vol = 0.0
                if len(cells) > 5 + off:
                    try:
                        vol = float(cells[5 + off])
                    except ValueError:
                        vol = 0.0
                if not (h >= max(o, c) and l <= min(o, c)):
                    raise ValueError(f"OHLC inconsistent O={o} H={h} L={l} C={c}")
                if any(v <= 0 for v in (o, h, l, c)):
                    raise ValueError("non-positive price")
                rows.append(Candle(canon, timeframe, _epoch_of_day(d), o, h, l, c, vol))
            except (ValueError, IndexError) as e:
                errors.append(f"{path}:{ln}: {e}")
    if errors:
        raise ValueError("CSV parse errors:\n" + "\n".join(errors[:10]))
    if not rows:
        raise ValueError(f"no candles found in {path}")
    rows.sort(key=lambda c: c.epoch)
    # dedupe same-day doubles (keep last)
    dedup: Dict[int, Candle] = {}
    for c in rows:
        dedup[c.epoch] = c
    return [dedup[k] for k in sorted(dedup)]


def load_data_dir(data_dir: str | Path) -> Tuple[Dict[str, List[Candle]], List[str]]:
    """Load every *.csv in dir; filename stem -> symbol via alias resolution.

    Returns (candles_by_canonical, missing_canonicals).
    """
    data_dir = Path(data_dir)
    out: Dict[str, List[Candle]] = {}
    if data_dir.is_dir():
        for p in sorted(data_dir.glob("*.csv")):
            canon = resolve_symbol(p.stem)
            if canon is None or canon not in CANONICAL_SYMBOLS:
                continue
            out[canon] = load_daily_csv(p, canon)
    missing = [c for c in CANONICAL_SYMBOLS if c not in out]
    return out, missing
