"""Cross-check the engine's swap math against YOUR terminal.

You read one number off the Deriv MT5 terminal for a real (demo) position:
for SYMBOL, SIDE, LOTS held over NIGHTS starting FROM-DATE, the terminal
shows a swap amount. This script replays the engine's own calculation
(trading.swaps.charge_for_range - the exact function the backtester calls)
and prints predicted vs observed side by side.

Usage:
    python3 scripts/check_swap.py --specs specs/specs.csv --symbol XAUUSD \\
        --side buy --lots 1.5 --nights 3 --from 2021-01-04 \\
        --observed -12.40 [--price 2350.0] [--stress 1.0]

--price: current/open price; required for INTEREST modes (annual % on
  price), ignored otherwise.
--from: first calendar date of the holding (YYYY-MM-DD). Triple-swap and
  weekend handling follow these dates, so use the real holding dates.
--observed: the swap figure from the terminal, in account currency,
  same sign convention (MT5 shows charges negative).

Exit code 0 on agreement within 1% (or 0.01 absolute for tiny amounts),
1 on mismatch - a mismatch means the mode conversion for that symbol is
wrong and must be fixed before trusting backtest swaps.
"""
import argparse
import csv
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from trading.swaps import MODE_NAMES, charge_for_range


def load_spec(path: str, symbol: str) -> dict:
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["canonical"].strip().upper() == symbol.strip().upper():
                return row
    raise SystemExit(f"symbol {symbol!r} not found in {path}")


def _num(row: dict, key: str, default: float = 0.0) -> float:
    v = row.get(key)
    return float(v) if v not in (None, "") else default


def build_swaps_entry(spec: dict) -> dict:
    """Raw-MT5 entry if mode columns present, else converted long/short."""
    if spec.get("swap_mode") not in (None, ""):
        return {
            "raw_long": _num(spec, "raw_swap_long"),
            "raw_short": _num(spec, "raw_swap_short"),
            "mode": int(float(spec["swap_mode"])),
            "point": _num(spec, "swap_point"),
            "contract_size": _num(spec, "contract_size") or 1.0,
            "tick_value": _num(spec, "swap_tick_value"),
            "tick_size": _num(spec, "swap_tick_size"),
            "triple_weekday": int(float(spec["triple_weekday"]))
            if spec.get("triple_weekday") not in (None, "") else None,
            "weekend_rollover": (spec.get("weekend_rollover") or "").lower() == "true",
        }
    return {
        "long": _num(spec, "swap_long_per_unit_night"),
        "short": _num(spec, "swap_short_per_unit_night"),
        "triple_weekday": int(float(spec["triple_weekday"]))
        if spec.get("triple_weekday") not in (None, "") else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", required=True)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--side", choices=["buy", "sell"], required=True)
    ap.add_argument("--lots", type=float, required=True)
    ap.add_argument("--nights", type=int, required=True)
    ap.add_argument("--from", dest="from_", required=True)
    ap.add_argument("--observed", type=float, required=True)
    ap.add_argument("--price", type=float, default=0.0)
    ap.add_argument("--stress", type=float, default=1.0)
    args = ap.parse_args()

    spec = load_spec(args.specs, args.symbol)
    sw = build_swaps_entry(spec)
    # drop None triple key so engine default (no triple) applies honestly
    sw = {k: v for k, v in sw.items() if v is not None}
    contract = _num(spec, "contract_size") or 1.0
    units = args.lots * contract
    d_from = dt.date.fromisoformat(args.from_)
    d_to = d_from + dt.timedelta(days=args.nights)

    predicted = charge_for_range(units=units, side=args.side, date_from=d_from,
                                 date_to=d_to, sw=sw, ref_price=args.price,
                                 cost_stress=args.stress)
    mode = spec.get("swap_mode_name") or MODE_NAMES.get(int(float(spec.get("swap_mode", 1))), "?")
    print(f"symbol   {args.symbol}  ({spec.get('mt5_name_raw', '?')})  mode {mode}")
    print(f"holding  {args.side} {args.lots} lots = {units:g} units, "
          f"{args.from_} + {args.nights} nights, stress {args.stress}")
    print(f"predicted {predicted:+.4f}   observed {args.observed:+.4f}   "
          f"diff {predicted - args.observed:+.4f}")
    tol = max(0.01, abs(args.observed) * 0.01)
    if abs(predicted - args.observed) <= tol:
        print("AGREE within tolerance.")
        return 0
    print("MISMATCH - do not trust this symbol's backtest swaps until resolved.")
    print("Common causes: wrong swap_mode mapping, missing FX conversion for")
    print("non-deposit-currency swaps, or a holiday rollover schedule.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
