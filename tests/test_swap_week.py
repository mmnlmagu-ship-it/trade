"""Monday-open to next-Monday-open must cost exactly 7 nights.

Weekends carry no rollover (market closed; the weekend cost is folded
into the triple day). Both Wednesday-triple and Friday-triple symbols:
1+1+3+1+1 = 7 night-equivalents. The engine previously charged calendar
nights (9) - this test pins the fix.
"""
import datetime as dt
import pytest
from trading.backtest import run_backtest
from trading.swaps import (ROLLOVER_FRIDAY, ROLLOVER_WEDNESDAY,
                           charge_for_range)
from trading.types import Candle, Signal

COSTS = {"spread_pips": 1.0, "pip_value_per_unit": 0.0001, "slippage_pips": 0.0}
# Real 2021 calendar: Fri 01-01, Mon 01-04 .. Fri 01-08, Mon 01-11
DAYS = [dt.date(2021, 1, d) for d in (1, 4, 5, 6, 7, 8, 11)]

def _bars():
    out = []
    for d in DAYS:
        epoch = int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp())
        out.append(Candle("EURUSD", "D1", epoch, 10.0, 10.05, 9.95, 10.0))
    return out

def _once(sym, hist):
    if len(hist) == 1:  # signal Friday -> filled Monday open -> held to next Monday
        return Signal(sym, "buy", hist[-1].close, atr=0.5, strategy="w", epoch=hist[-1].epoch)
    return None

@pytest.mark.parametrize("triple", [ROLLOVER_WEDNESDAY, ROLLOVER_FRIDAY])
def test_monday_to_monday_is_seven_nights(triple):
    r = run_backtest(candles_by_symbol={"EURUSD": _bars()}, strategy=_once,
                     costs_by_symbol={"EURUSD": COSTS},
                     swaps_by_symbol={"EURUSD": {"long": -2.0, "short": 0.0,
                                                 "triple_weekday": triple}},
                     starting_equity=10_000)
    assert len(r.trades) == 1
    t = r.trades[0]
    # units = 1% of 10k / (2*0.5) = 100; notional 100*10 = 1000 <= 25% cap OK
    assert t.units == pytest.approx(100.0)
    assert t.swap_total == pytest.approx(100 * -2.0 * 7)
    assert r.stats["total_swaps"] == pytest.approx(100 * -2.0 * 7)

def test_charge_for_range_agrees_with_week():
    sw = {"long": -2.0, "short": 0.0, "triple_weekday": ROLLOVER_WEDNESDAY}
    assert charge_for_range(units=100, side="buy", date_from=DAYS[1], date_to=DAYS[6],
                            sw=sw) == pytest.approx(100 * -2.0 * 7)
