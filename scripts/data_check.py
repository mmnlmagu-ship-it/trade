"""Data-check: years of history per symbol + spread/swap per symbol.

Usage:
    python3 scripts/data_check.py --data data --specs specs/specs.csv

CSVs: one per symbol, filename stem = symbol spelling on YOUR Deriv MT5
demo (aliases resolved, e.g. `US Oil.csv`, `XAUUSD.s.csv`).
Specs CSV: use the exporter output (scripts/mt5_export.py) directly, or
specs/specs_template.csv as a starting point. Raw MT5 swap rates
(raw_swap_long/short + swap_mode) are converted to per-unit-night costs
for review; converted swap_long_per_unit_night wins if already filled.

Also flags daily bars gapping over 5 ATR for manual review.

Exit code 1 if any canonical symbol has no CSV.
"""
import argparse
import csv
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from trading.csv_loader import load_data_dir
from trading.gaps import flag_gaps
from trading.mt5_symbols import CANONICAL_SYMBOLS, DERIV_PRODUCT_NAMES
from trading.swaps import DAY_NAMES, MODE_NAMES


def load_specs(path: Path):
    specs = {}
    if path.is_file():
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                specs[row["canonical"].strip().upper()] = row
    return specs


def years_between(first_epoch: int, last_epoch: int) -> float:
    return (last_epoch - first_epoch) / (365.25 * 86400)


def _f(x, default="?"):
    return x if x not in (None, "") else default


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--specs", default="specs/specs.csv")
    args = ap.parse_args()
    n = len(CANONICAL_SYMBOLS)

    by_sym, missing = load_data_dir(args.data)
    specs = load_specs(Path(args.specs))

    print(f"{'symbol':<8}{'product':<16}{'bars':>6}{'first':>12}{'last':>12}{'yrs':>6}  "
          f"{'spread':>10}  {'swapL/u/n':>10}  {'swapS/u/n':>10}  {'mode':<16}  {'3x-day':<9}")
    print("-" * 128)
    for canon in CANONICAL_SYMBOLS:
        prod = DERIV_PRODUCT_NAMES[canon]
        spec = specs.get(canon, {})
        spread = _f(spec.get("spread_price_units"))
        swl = _f(spec.get("swap_long_per_unit_night"))
        sws = _f(spec.get("swap_short_per_unit_night"))
        mode = spec.get("swap_mode_name") or ""
        if not mode:
            try:
                mode = MODE_NAMES.get(int(spec["swap_mode"]), "?") if spec.get("swap_mode") not in (None, "") else "?"
            except (ValueError, TypeError):
                mode = str(spec.get("swap_mode"))
        try:
            t3 = DAY_NAMES[int(spec["triple_weekday"])] if spec.get("triple_weekday") not in (None, "") else "?"
        except (ValueError, TypeError, IndexError):
            t3 = "?"
        if canon in by_sym:
            bars = by_sym[canon]
            f = dt.datetime.fromtimestamp(bars[0].epoch, dt.timezone.utc).date().isoformat()
            l = dt.datetime.fromtimestamp(bars[-1].epoch, dt.timezone.utc).date().isoformat()
            y = years_between(bars[0].epoch, bars[-1].epoch)
            print(f"{canon:<8}{prod:<16}{len(bars):>6}{f:>12}{l:>12}{y:>6.2f}  "
                  f"{spread:>10}  {swl:>10}  {sws:>10}  {mode:<16}  {t3:<9}")
        else:
            print(f"{canon:<8}{prod:<16}{'MISSING':>6}  -- export D1 CSV from YOUR Deriv MT5 demo "
                  f"(run scripts/mt5_export.py on Windows)")
    print("-" * 128)
    if missing:
        print(f"MISSING {len(missing)}/{n}: {', '.join(missing)}. No backtest runs until all load.")
        return 1
    if not specs:
        print(f"WARNING: specs file {args.specs} not found - spread/swap unknown. "
              "Backtest will REFUSE to run without per-symbol costs.")
        return 1
    gaps = flag_gaps(by_sym)
    if gaps:
        print(f"GAP REVIEW: {len(gaps)} daily bar(s) gapping over 5 ATR - check manually:")
        for g in gaps[:20]:
            d = dt.datetime.fromtimestamp(g.epoch, dt.timezone.utc).date().isoformat()
            print(f"  {g.symbol} {d}: gap {g.gap:+.5f} = {g.gap_atr:+.1f} ATR")
        if len(gaps) > 20:
            print(f"  ... and {len(gaps) - 20} more")
    else:
        print("Gaps: none over 5 ATR.")
    print(f"OK: all {n} symbols loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
