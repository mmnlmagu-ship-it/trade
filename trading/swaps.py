"""MT5 swap-mode conversion + triple-swap-day handling.

MT5 reports SYMBOL_SWAP_LONG/SHORT in units given by SYMBOL_SWAP_MODE
(ENUM_SYMBOL_SWAP_MODE, MQL5 docs:
https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants
and https://www.mql5.com/en/book/automation/symbols/symbols_swaps):

  0 DISABLED            swaps off (rate must be 0)
  1 POINTS              rate in points
  2 CURRENCY_SYMBOL     money in base currency, per lot
  3 CURRENCY_MARGIN     money in margin currency, per lot
  4 CURRENCY_DEPOSIT    money in deposit currency, per lot
  5 CURRENCY_PROFIT     money in profit currency, per lot
  6 INTEREST_CURRENT    annual % on current price, 360-day year
  7 INTEREST_OPEN       annual % on position open price, 360-day year
  8 REOPEN_CURRENT      reopen at prior close +/- points (approx as points)
  9 REOPEN_BID          reopen at new-day Bid +/- points (approx as points)

Our engine prices positions in `units` of base currency, so everything is
converted to **account-currency per unit per night**. Currency-mode rates
are per-lot quotes (documented MT5 convention), hence divided by
contract_size. tick_value conversions assume profit==deposit currency;
cross-currency cases are flagged, not silently converted.

SYMBOL_SWAP_ROLLOVER3DAYS is a weekday enum (0=Sunday..6=Saturday,
ENUM_DAY_OF_WEEK). The rolloverHeld across that weekday's date boundary
is charged 3x. Deriv FX commonly uses Wednesday but the terminal value
wins - never assume.
"""
from typing import Dict, Tuple

# Named MT5 constants (ENUM_SYMBOL_SWAP_MODE values, MQL5 reference).
# Use these names everywhere - never bare integers. They mirror the
# MetaTrader5 Python package names (mt5.SYMBOL_SWAP_MODE_POINTS etc.);
# scripts/mt5_export.py prefers mt5.<NAME> when the package exposes it
# and falls back to these values otherwise.
SWAP_MODE_DISABLED = 0
SWAP_MODE_POINTS = 1
SWAP_MODE_CURRENCY_SYMBOL = 2
SWAP_MODE_CURRENCY_MARGIN = 3
SWAP_MODE_CURRENCY_DEPOSIT = 4
SWAP_MODE_CURRENCY_PROFIT = 5
SWAP_MODE_INTEREST_CURRENT = 6
SWAP_MODE_INTEREST_OPEN = 7
SWAP_MODE_REOPEN_CURRENT = 8
SWAP_MODE_REOPEN_BID = 9

# MT5 weekday enum (ENUM_DAY_OF_WEEK): Sunday=0 .. Saturday=6.
ROLLOVER_SUNDAY = 0
ROLLOVER_MONDAY = 1
ROLLOVER_TUESDAY = 2
ROLLOVER_WEDNESDAY = 3
ROLLOVER_THURSDAY = 4
ROLLOVER_FRIDAY = 5
ROLLOVER_SATURDAY = 6

MODE_NAMES = {
    SWAP_MODE_DISABLED: "DISABLED", SWAP_MODE_POINTS: "POINTS",
    SWAP_MODE_CURRENCY_SYMBOL: "CURRENCY_SYMBOL",
    SWAP_MODE_CURRENCY_MARGIN: "CURRENCY_MARGIN",
    SWAP_MODE_CURRENCY_DEPOSIT: "CURRENCY_DEPOSIT",
    SWAP_MODE_CURRENCY_PROFIT: "CURRENCY_PROFIT",
    SWAP_MODE_INTEREST_CURRENT: "INTEREST_CURRENT",
    SWAP_MODE_INTEREST_OPEN: "INTEREST_OPEN",
    SWAP_MODE_REOPEN_CURRENT: "REOPEN_CURRENT",
    SWAP_MODE_REOPEN_BID: "REOPEN_BID",
}

DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday",
             "Friday", "Saturday"]


def mode_name(mode: int) -> str:
    if mode not in MODE_NAMES:
        raise ValueError(f"unknown MT5 swap mode {mode!r}")
    return MODE_NAMES[mode]


def mt5_to_per_unit_night(
    *,
    mode: int,
    raw_rate: float,
    point: float,
    contract_size: float,
    tick_value: float = 0.0,
    tick_size: float = 0.0,
    ref_price: float = 0.0,
) -> Tuple[float, str]:
    """Convert one raw MT5 swap rate to account-ccy per unit per night.

    Returns (rate, note). `note` is non-empty when the result is an
    approximation needing manual review (interest/reopen/cross-currency).
    """
    if contract_size <= 0:
        raise ValueError("contract_size must be positive")
    if mode == SWAP_MODE_DISABLED:
        if raw_rate != 0:
            raise ValueError("swap DISABLED but non-zero rate - check terminal")
        return 0.0, ""
    if mode == SWAP_MODE_POINTS:  # POINTS: cash ~= points * point * contract * lots; per unit = rate*point
        if point <= 0:
            raise ValueError("point must be positive for POINTS mode")
        return raw_rate * point, ""
    if mode in (SWAP_MODE_CURRENCY_SYMBOL, SWAP_MODE_CURRENCY_MARGIN,
                SWAP_MODE_CURRENCY_DEPOSIT, SWAP_MODE_CURRENCY_PROFIT):  # per-lot money -> per unit
        rate = raw_rate / contract_size
        note = "" if mode == SWAP_MODE_CURRENCY_DEPOSIT else "approx: non-deposit-currency swap, no FX conversion applied"
        return rate, note
    if mode in (SWAP_MODE_INTEREST_CURRENT, SWAP_MODE_INTEREST_OPEN):  # annual % on price, 360-day year
        if ref_price <= 0:
            raise ValueError("ref_price must be positive for INTEREST modes")
        return raw_rate / 100.0 * ref_price / 360.0, "approx: interest-mode linearisation"
    if mode in (SWAP_MODE_REOPEN_CURRENT, SWAP_MODE_REOPEN_BID):  # reopen +/- points
        if point <= 0:
            raise ValueError("point must be positive for REOPEN modes")
        return raw_rate * point, "approx: reopen-mode linearisation"
    raise ValueError(f"unknown MT5 swap mode {mode!r}")


def weekday_ratios(triple_weekday: int, weekend_rollover: bool = False) -> Dict[int, int]:
    """MT5-style per-weekday rollover ratios.

    FX/CFD markets are closed on weekends, so Saturday/Sunday boundaries
    carry 0x by default (the weekend cost is folded into the triple day -
    that is exactly why Wednesday counts 3x). Set weekend_rollover=True
    only for 24/7 symbols.
    """
    if not (ROLLOVER_SUNDAY <= triple_weekday <= ROLLOVER_SATURDAY):
        raise ValueError("triple_weekday must be 0..6 (MT5 Sunday=0)")
    ratios = {ROLLOVER_SUNDAY: 0, ROLLOVER_MONDAY: 1, ROLLOVER_TUESDAY: 1,
              ROLLOVER_WEDNESDAY: 1, ROLLOVER_THURSDAY: 1, ROLLOVER_FRIDAY: 1,
              ROLLOVER_SATURDAY: 0}
    if weekend_rollover:
        ratios[ROLLOVER_SUNDAY] = 1
        ratios[ROLLOVER_SATURDAY] = 1
    ratios[triple_weekday] = 3
    return ratios


def nightly_multipliers(date_from, date_to, triple_weekday: int,
                        weekend_rollover: bool = False) -> list:
    """Per-night multipliers for the date roll [date_from, date_to).

    Each calendar-night boundary gets its weekday ratio (see
    weekday_ratios): 1x normally, 3x on triple_weekday, 0x on closed
    weekends. MT5 weekday: (python_weekday + 1) % 7.
    """
    import datetime as _dt
    ratios = weekday_ratios(triple_weekday, weekend_rollover)
    out = []
    d = date_from
    while d < date_to:
        mt5_dow = (d.weekday() + 1) % 7
        out.append(ratios[mt5_dow])
        d += _dt.timedelta(days=1)
    if not out:
        out = [1]
    return out


def trading_nights(date_from, date_to) -> int:
    """Count of Mon-Fri night boundaries in [date_from, date_to), min 1."""
    import datetime as _dt
    n = 0
    d = date_from
    while d < date_to:
        if (d.weekday() + 1) % 7 not in (ROLLOVER_SUNDAY, ROLLOVER_SATURDAY):
            n += 1
        d += _dt.timedelta(days=1)
    return max(1, n)


def resolve_swap(sw: Dict, side: str, ref_price: float = 0.0) -> Tuple[float, str]:
    """Per-unit-night account-ccy rate from an engine swaps entry.

    Converted form: {"long": x, "short": y, ...} used as-is.
    Raw MT5 form: {"raw_long"/"raw_short", "mode", "point",
    "contract_size", ...} converted via mt5_to_per_unit_night.
    """
    if "mode" not in sw:
        return (sw.get("long", 0.0) if side == "buy" else sw.get("short", 0.0)), ""
    raw = sw.get("raw_long", 0.0) if side == "buy" else sw.get("raw_short", 0.0)
    price = ref_price if sw.get("mode") in (SWAP_MODE_INTEREST_CURRENT,
                                            SWAP_MODE_INTEREST_OPEN) else sw.get("ref_price", ref_price)
    return mt5_to_per_unit_night(mode=int(sw["mode"]), raw_rate=raw,
                                 point=sw.get("point", 0.0),
                                 contract_size=sw.get("contract_size", 0.0),
                                 tick_value=sw.get("tick_value", 0.0),
                                 tick_size=sw.get("tick_size", 0.0),
                                 ref_price=price or 0.0)


def charge_for_range(*, units: float, side: str, date_from, date_to,
                     sw: Dict, ref_price: float = 0.0,
                     cost_stress: float = 1.0) -> float:
    """Total swap for holding `units` over [date_from, date_to).

    Single source of truth shared by the backtest engine and
    scripts/check_swap.py, so the two agree by construction.
    """
    from trading.costs import overnight_swap
    rate, _note = resolve_swap(sw, side, ref_price=ref_price)
    rate *= cost_stress
    long_r = rate if side == "buy" else 0.0
    short_r = rate if side == "sell" else 0.0
    if "triple_weekday" in sw and sw["triple_weekday"] not in (None, ""):
        mults = nightly_multipliers(date_from, date_to, int(sw["triple_weekday"]),
                                    bool(sw.get("weekend_rollover", False)))
        return sum(overnight_swap(units=units, side=side, nights=1,
                                  swap_long_per_unit_night=long_r,
                                  swap_short_per_unit_night=short_r,
                                  multiplier=m) for m in mults)
    return overnight_swap(units=units, side=side,
                          nights=trading_nights(date_from, date_to),
                          swap_long_per_unit_night=long_r,
                          swap_short_per_unit_night=short_r)
