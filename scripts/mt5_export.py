"""Export Deriv MT5 demo data on YOUR Windows machine (MT5 is not reachable
from the Linux dev VM, so this script runs where your terminal lives).

READ-ONLY by design: it calls only initialize/copy_rates/symbol_info.
There are no order functions in this file - consistent with the standing
rule of no live trading code.

On your Windows machine, with MT5 open and logged into your Deriv demo:
    pip install MetaTrader5
    python mt5_export.py --out data_out --count 5000

Then send back the whole data_out/ folder (6 price CSVs + specs.csv +
symbols_found.txt). The dev-VM side (csv_loader + data_check) reads the
price CSVs unchanged; specs.csv drops straight into specs/.

Symbol mapping: Deriv demo spellings vary by server (suffixes like .s,
descriptive names like "US Oil"). The script searches YOUR terminal's
symbol list with the alias map from trading/mt5_symbols.py and reports
exactly what it matched in symbols_found.txt - if a match looks wrong,
tell us and we fix the alias, not your data.

NOTE (honest): the MetaTrader5 calls below follow the documented Python
API but were NOT executed here (no Windows/MT5 in this VM). If you hit
an error, paste the full traceback back and we fix it.
"""
import argparse
import csv
import datetime as _dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from trading.mt5_symbols import CANONICAL_SYMBOLS  # alias map lives here too
from trading import swaps as _swaps  # named MT5 constants + mode names

# Candidate spellings to search on YOUR terminal, in preference order.
CANDIDATES = {
    "EURUSD": ["EURUSD", "EURUSD.s", "EURUSD.a"],
    "GBPUSD": ["GBPUSD", "GBPUSD.s"],
    "USDJPY": ["USDJPY", "USDJPY.s"],
    "AUDUSD": ["AUDUSD", "AUDUSD.s"],
    "USDCAD": ["USDCAD", "USDCAD.s"],
    "XAUUSD": ["XAUUSD", "XAUUSD.s", "XAUUSD.a", "GOLD"],
    "XAGUSD": ["XAGUSD", "XAGUSD.s", "SILVER"],
    "USOIL": ["US Oil", "USOil", "USOIL", "WTI"],
    "UKOIL": ["UK Brent Oil", "UKOIL", "BRENT"],
    "US30": ["Wall Street 30", "US30", "WS30"],
    "US500": ["US SP 500", "US500", "SPX500"],
    "USTEC": ["US Tech 100", "USTEC", "NAS100"],
}

TIMEFRAME_NAME = "D1"


def mt5_const(mt5, name: str, fallback: int) -> int:
    """Prefer the MetaTrader5 package constant; fall back to trading/swaps.py."""
    return getattr(mt5, name, fallback)


def check_mt5_constants(mt5) -> None:
    """Self-check on YOUR machine: package constants must match trading/swaps.py.

    Prints warnings only - a missing constant falls back silently, a
    MISMATCHED one is loud, because that would mean our mode conversion is
    wrong for this terminal.
    """
    pairs = [(f"SYMBOL_SWAP_MODE_{n}", v) for n, v in _swaps.MODE_NAMES.items()]
    for attr, ours in pairs:
        theirs = getattr(mt5, attr, None)
        if theirs is None:
            print(f"  note: mt5.{attr} not exposed by this package build; using {ours}")
        elif int(theirs) != ours:
            print(f"  WARNING: mt5.{attr}={theirs} != trading/swaps.py {ours}. "
                  "Paste this into the chat before trusting swap conversions.")


def check_demo_account(mt5):
    """Refuse anything that is not a Deriv demo account. Returns (login, server)."""
    acct = mt5.account_info()
    if acct is None:
        raise SystemExit("No MT5 account logged in - log into your Deriv DEMO first.")
    print("Checking MetaTrader5 constant map...")
    check_mt5_constants(mt5)
    demo_mode = mt5_const(mt5, "ACCOUNT_TRADE_MODE_DEMO", 2)
    server = (acct.server or "")
    if acct.trade_mode != demo_mode or "demo" not in server.lower():
        raise SystemExit(
            f"REFUSING: account {acct.login} on '{server}' is not a demo "
            f"account (trade_mode={acct.trade_mode}). Log into the Deriv "
            "demo account and re-run. Nothing was exported.")
    print(f"Demo check OK: login {acct.login} on '{server}'.")
    return acct.login, server


def discover(mt5, candidates):
    """Return {canonical: terminal_symbol}. Raises if any canonical missing."""
    found = {}
    all_syms = [s.name for s in mt5.symbols_get()]
    for canon, tries in candidates.items():
        match = next((t for t in tries if t in all_syms), None)
        if match is None:
            lowered = {a.lower(): a for a in all_syms}
            for t in tries:
                if t.lower() in lowered:
                    match = lowered[t.lower()]
                    break
        if match is None:
            hints = sorted(a for a in all_syms
                           if canon[:3].lower() in a.lower()
                           or any(w in a.lower() for w in ("oil", "gold", "street", "tech", "500", "30")))
            raise SystemExit(
                f"Could not find {canon} on your terminal.\n"
                f"Tried: {tries}\nPossible lookalikes: {hints[:20]}\n"
                "Open Market Watch, right-click -> Symbols, enable it, re-run.")
        found[canon] = match
    return found


def export_symbol(mt5, terminal_symbol, canon, outdir, count):
    mt5.symbol_select(terminal_symbol, True)
    rates = mt5.copy_rates_from_pos(terminal_symbol,
                                    mt5_const(mt5, "TIMEFRAME_D1", 16408), 0, count)
    if rates is None or len(rates) == 0:
        raise SystemExit(f"No D1 history for {terminal_symbol}: "
                         f"{mt5.last_error()}. Scroll the D1 chart left to load history, re-run.")
    path = outdir / f"{canon}.csv"  # canonical filename: loader resolves it
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["DATE", "TIME", "OPEN", "HIGH", "LOW", "CLOSE", "TICKVOL", "VOL", "SPREAD"])
        for r in rates:
            d = _dt.datetime.fromtimestamp(int(r["time"]), _dt.timezone.utc).date()
            w.writerow([d.strftime("%Y.%m.%d"), "00:00", r["open"], r["high"],
                        r["low"], r["close"], int(r["tick_volume"]), int(r["real_volume"]),
                        int(r["spread"])])
    info = mt5.symbol_info(terminal_symbol)
    spec = {
        "canonical": canon, "mt5_name_raw": terminal_symbol,
        "contract_size": info.trade_contract_size,
        "spread_price_units": info.spread * info.point,
        # raw MT5 swap rates + mode: the engine converts per mode
        # (see trading/swaps.py). Converted per-unit-night columns are
        # filled by scripts/data_check.py for review.
        "raw_swap_long": info.swap_long,
        "raw_swap_short": info.swap_short,
        "swap_mode": info.swap_mode,
        "swap_mode_name": _swaps.MODE_NAMES.get(int(info.swap_mode), "UNKNOWN"),
        "swap_point": info.point,
        "swap_tick_value": info.tick_value,
        "swap_tick_size": info.trade_tick_size,
        "triple_weekday": info.swap_rollover3days,
        "swap_long_per_unit_night": "",
        "swap_short_per_unit_night": "",
        "notes": f"digits={info.digits} exported={len(rates)} bars",
    }
    return path, spec, len(rates)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data_out")
    ap.add_argument("--count", type=int, default=5000)
    args = ap.parse_args()
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("MetaTrader5 package missing: run  pip install MetaTrader5  on this machine.")
        return 2
    if not mt5.initialize():
        print(f"mt5.initialize() failed: {mt5.last_error()}. "
              "Open your MT5 terminal and log into the Deriv demo first.")
        return 2
    try:
        check_demo_account(mt5)
    except SystemExit as e:
        mt5.shutdown()
        return e.code
    try:
        outdir = Path(args.out)
        (outdir / "prices").mkdir(parents=True, exist_ok=True)
        found = discover(mt5, CANDIDATES)
        (outdir / "symbols_found.txt").write_text(
            "\n".join(f"{c} -> {t}" for c, t in found.items()) + "\n")
        specs = []
        for canon in CANONICAL_SYMBOLS:
            path, spec, n = export_symbol(mt5, found[canon], canon, outdir / "prices", args.count)
            specs.append(spec)
            print(f"{canon:<8} {found[canon]:<18} {n:>5} bars -> {path}")
        with open(outdir / "specs.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(specs[0].keys()))
            w.writeheader()
            w.writerows(specs)
        print(f"\nDone. Send back: {outdir}/prices/*.csv, specs.csv, symbols_found.txt")
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
