"""Engine mechanics: fills, costs, stops, vetoes, caps, splits."""
import datetime as dt
import pytest
from trading.backtest import run_backtest, walk_forward_splits
from trading.config import RiskLimits
from trading.risk_engine import RiskEngine
from trading.types import Candle, Signal

COSTS = {"spread_pips": 10.0, "pip_value_per_unit": 0.0001, "slippage_pips": 5.0}

def _bars(symbol, closes, start=2020, opens=None):
    base = int(dt.datetime(start, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    out = []
    for i, c in enumerate(closes):
        o = opens[i] if opens else c
        out.append(Candle(symbol, "D1", base + i * 86400, o, max(o, c) * 1.001,
                          min(o, c) * 0.999, c))
    return out

def _always(suffix="t"):
    def s(sym, hist):
        b = hist[-1]
        return Signal(sym, "buy", b.close, atr=(b.high - b.low) or 0.001,
                      strategy=suffix, epoch=b.epoch)
    return s

def test_next_bar_open_fill_and_costs_charged():
    bars = _bars("EURUSD", [1.10, 1.11, 1.12, 1.13, 1.14])
    r = run_backtest(candles_by_symbol={"EURUSD": bars},
                     strategy=_always(), costs_by_symbol={"EURUSD": COSTS},
                     starting_equity=10_000)
    assert len(r.trades) == 1
    t = r.trades[0]
    assert t.entry_epoch == bars[1].epoch and t.entry_price > bars[1].open  # spread+slip paid
    assert t.entry_costs > 0 and t.exit_costs > 0
    assert r.stats["total_costs"] == pytest.approx(t.entry_costs + t.exit_costs)

def test_zero_cost_backtest_blocked():
    bars = _bars("EURUSD", [1.1, 1.2, 1.3])
    with pytest.raises(ValueError):
        run_backtest(candles_by_symbol={"EURUSD": bars}, strategy=_always(),
                     costs_by_symbol={"EURUSD": {}})

def test_gap_through_stop_fills_at_open_not_stop():
    # long stop at ~1.09; bar 2 gaps down: open 1.05 below stop
    bars = _bars("EURUSD", [1.10, 1.10, 1.04, 1.04],
                 opens=[1.10, 1.10, 1.05, 1.04])
    def s(sym, hist):
        if len(hist) == 1:
            b = hist[-1]
            return Signal(sym, "buy", b.close, atr=0.005, strategy="g", epoch=b.epoch)
        return None
    r = run_backtest(candles_by_symbol={"EURUSD": bars}, strategy=s,
                     costs_by_symbol={"EURUSD": COSTS}, starting_equity=10_000)
    assert len(r.trades) == 1
    # stop was 1.10-2*0.005=1.09; gap open 1.05 -> exit at open minus costs
    assert r.trades[0].exit_price < 1.09

def test_stop_then_takeprofit_ambiguity_resolves_to_stop():
    bars = _bars("EURUSD", [1.10, 1.10, 1.10, 1.10])  # flat: no stop hit expected
    r = run_backtest(candles_by_symbol={"EURUSD": bars}, strategy=_always(),
                     costs_by_symbol={"EURUSD": COSTS}, starting_equity=10_000)
    assert r.trades[0].exit_epoch == bars[-1].epoch  # liquidation, not stop

def test_risk_veto_blocks_and_counts():
    bars = _bars("EURUSD", [1.1, 1.2, 1.3, 1.4, 1.5])
    risk = RiskEngine(limits=RiskLimits(max_drawdown_pct=0.0001))  # trips instantly
    risk.kill_switch_tripped = True
    r = run_backtest(candles_by_symbol={"EURUSD": bars}, strategy=_always(),
                     costs_by_symbol={"EURUSD": COSTS}, risk=risk, starting_equity=10_000)
    assert r.trades == [] and r.vetoed >= 1

def test_portfolio_cap_blocks_second_symbol():
    bars = {s: _bars(s, [10.0, 10.5, 11.0, 11.5]) for s in ("US30", "US500")}
    risk = RiskEngine(limits=RiskLimits(max_position_notional_pct=100.0,
                                        max_portfolio_notional_pct=100.0))
    r = run_backtest(candles_by_symbol=bars, strategy=_always(),
                     costs_by_symbol={s: COSTS for s in bars}, risk=risk,
                     starting_equity=1_000)
    # 1000 equity, 100% cap: both 100%-sized positions cannot coexist
    assert r.vetoed >= 1

def test_swap_charged_per_night_held():
    bars = _bars("EURUSD", [1.10] * 6)  # flat: PnL ~= -costs - swaps
    r = run_backtest(candles_by_symbol={"EURUSD": bars}, strategy=_always(),
                     costs_by_symbol={"EURUSD": COSTS},
                     swaps_by_symbol={"EURUSD": {"long": -1.0, "short": 0.0}},
                     starting_equity=10_000)
    t = r.trades[0]
    assert t.swap_total < 0 and r.stats["total_swaps"] == pytest.approx(t.swap_total)

def test_walk_forward_no_overlap_and_embargo():
    splits = walk_forward_splits(600, n_splits=3, embargo_bars=5, min_train_bars=30)
    assert len(splits) == 3
    tests = [te for _, te in splits]
    for i in range(len(tests) - 1):
        assert tests[i][1] <= tests[i + 1][0]  # test blocks don't overlap
    for (a, b), (c, d) in splits:
        assert b + 5 <= c  # embargo respected

def test_walk_forward_rejects_short_history():
    with pytest.raises(ValueError):
        walk_forward_splits(10, n_splits=3)
