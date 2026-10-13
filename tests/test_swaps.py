import datetime as dt
import pytest
from trading.swaps import (DAY_NAMES, MODE_NAMES, ROLLOVER_WEDNESDAY,
                           SWAP_MODE_CURRENCY_DEPOSIT, SWAP_MODE_DISABLED,
                           SWAP_MODE_INTEREST_CURRENT, SWAP_MODE_POINTS,
                           mode_name, mt5_to_per_unit_night,
                           nightly_multipliers, resolve_swap, weekday_ratios)

def test_points_mode_deriv_fx():
    # Deriv specs quote FX swaps in points ("Swap long (pts)")
    rate, note = mt5_to_per_unit_night(mode=SWAP_MODE_POINTS, raw_rate=-5.0, point=0.00001,
                                       contract_size=100_000)
    assert rate == pytest.approx(-5e-05) and note == ""

def test_disabled_mode():
    assert mt5_to_per_unit_night(mode=SWAP_MODE_DISABLED, raw_rate=0.0, point=1.0, contract_size=1) == (0.0, "")
    with pytest.raises(ValueError):
        mt5_to_per_unit_night(mode=SWAP_MODE_DISABLED, raw_rate=-1.0, point=1.0, contract_size=1)

def test_currency_deposit_is_per_lot():
    rate, _ = mt5_to_per_unit_night(mode=SWAP_MODE_CURRENCY_DEPOSIT, raw_rate=-10.0, point=0.01, contract_size=100)
    assert rate == pytest.approx(-0.10)

def test_interest_mode_uses_360_day_year():
    rate, note = mt5_to_per_unit_night(mode=SWAP_MODE_INTEREST_CURRENT, raw_rate=-3.65, point=1.0,
                                       contract_size=1, ref_price=100.0)
    assert rate == pytest.approx(-3.65 / 100 * 100 / 360) and note != ""

def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        mt5_to_per_unit_night(mode=99, raw_rate=1.0, point=1.0, contract_size=1)
    with pytest.raises(ValueError):
        mode_name(99)

def test_triple_swap_wednesday_fx():
    # Closed weekends carry 0x; the weekend cost lives inside Wednesday's 3x.
    fri, mon = dt.date(2021, 1, 1), dt.date(2021, 1, 4)
    assert nightly_multipliers(fri, mon, ROLLOVER_WEDNESDAY) == [1, 0, 0]
    # Tue->Thu crosses Wednesday's boundary -> one 3x night
    assert nightly_multipliers(dt.date(2021, 1, 5), dt.date(2021, 1, 7),
                               ROLLOVER_WEDNESDAY) == [1, 3]
    # Full week Mon->Mon: 1+1+3+1+1+0+0 = exactly 7 night-equivalents
    assert sum(nightly_multipliers(dt.date(2021, 1, 4), dt.date(2021, 1, 11),
                                   ROLLOVER_WEDNESDAY)) == 7


def test_weekday_ratios_closed_weekends_by_default():
    r = weekday_ratios(ROLLOVER_WEDNESDAY)
    assert (r[0], r[6]) == (0, 0) and r[ROLLOVER_WEDNESDAY] == 3
    r247 = weekday_ratios(ROLLOVER_WEDNESDAY, weekend_rollover=True)
    assert (r247[0], r247[6]) == (1, 1)

def test_bad_triple_weekday_rejected():
    with pytest.raises(ValueError):
        nightly_multipliers(dt.date(2021, 1, 1), dt.date(2021, 1, 2), 7)

def test_resolve_converted_and_raw_forms():
    assert resolve_swap({"long": -0.02, "short": -0.01}, "buy") == (-0.02, "")
    rate, note = resolve_swap({"raw_long": -5.0, "raw_short": -2.0, "mode": SWAP_MODE_POINTS,
                               "point": 0.00001, "contract_size": 100_000}, "sell")
    assert rate == pytest.approx(-2e-05)
