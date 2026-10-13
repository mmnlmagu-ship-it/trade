import datetime as dt
import pytest
from trading.backtest import run_backtest
from trading.types import Candle, Signal

COSTS = {"spread_pips": 10.0, "pip_value_per_unit": 0.0001, "slippage_pips": 5.0}

def _bars():
    base = int(dt.datetime(2021, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    return [Candle("EURUSD", "D1", base + i * 86400, 1.10, 1.11, 1.09, 1.10 + i * 0.0005)
            for i in range(10)]

def _always(sym, hist):
    b = hist[-1]
    return Signal(sym, "buy", b.close, atr=0.002, strategy="s", epoch=b.epoch)

def test_stress_levels_accepted_and_recorded():
    for level in (1.0, 1.5, 2.0):
        r = run_backtest(candles_by_symbol={"EURUSD": _bars()}, strategy=_always,
                         costs_by_symbol={"EURUSD": COSTS}, starting_equity=10_000,
                         cost_stress=level)
        assert r.stats["cost_stress"] == level

def test_higher_stress_costs_more():
    tots = []
    for level in (1.0, 1.5, 2.0):
        r = run_backtest(candles_by_symbol={"EURUSD": _bars()}, strategy=_always,
                         costs_by_symbol={"EURUSD": COSTS}, starting_equity=10_000,
                         cost_stress=level)
        tots.append(r.stats["total_costs"])
    assert tots[0] < tots[1] < tots[2]

def test_stress_scales_swaps():
    sw = {"EURUSD": {"long": -1.0, "short": 0.0}}
    r1 = run_backtest(candles_by_symbol={"EURUSD": _bars()}, strategy=_always,
                      costs_by_symbol={"EURUSD": COSTS}, swaps_by_symbol=sw,
                      starting_equity=10_000, cost_stress=1.0)
    r2 = run_backtest(candles_by_symbol={"EURUSD": _bars()}, strategy=_always,
                      costs_by_symbol={"EURUSD": COSTS}, swaps_by_symbol=sw,
                      starting_equity=10_000, cost_stress=2.0)
    assert r2.stats["total_swaps"] == pytest.approx(2 * r1.stats["total_swaps"])

def test_invalid_stress_rejected():
    with pytest.raises(ValueError):
        run_backtest(candles_by_symbol={"EURUSD": _bars()}, strategy=_always,
                     costs_by_symbol={"EURUSD": COSTS}, cost_stress=3.0)
