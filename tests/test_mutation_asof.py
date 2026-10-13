"""Mutation test: disable the as_of clamp and confirm protection collapses.

If someone (or some refactor) breaks `_history_upto`, the guards must
visibly fail - otherwise the look-ahead tests would be theatre.
"""
import datetime as dt
import pytest
import trading.backtest as bt
from trading.types import Candle, Signal

COSTS = {"spread_pips": 1.5, "pip_value_per_unit": 0.0001, "slippage_pips": 0.5}

def _bars(closes):
    base = int(dt.datetime(2021, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    return [Candle("EURUSD", "D1", base + i * 86400, c, c * 1.001, c * 0.999, c)
            for i, c in enumerate(closes)]

def test_history_invariant_breaks_when_clamp_removed(monkeypatch):
    bars = _bars([1.0, 2.0, 3.0, 4.0])
    seen = []
    def s(sym, hist):
        seen.append(max(b.epoch for b in hist))
        b = hist[-1]
        return Signal(sym, "buy", b.close, atr=0.01, strategy="m", epoch=b.epoch)
    monkeypatch.setattr(bt, "_history_upto", lambda bars, i: bars)  # THE MUTATION
    bt.run_backtest(candles_by_symbol={"EURUSD": bars}, strategy=s,
                    costs_by_symbol={"EURUSD": COSTS})
    leaked = [mx for k, mx in enumerate(seen) if mx != bars[k].epoch]
    assert leaked, "mutant must leak future bars past as_of (else the test is blind)"

def test_history_only_cheater_wins_only_when_clamp_removed(monkeypatch):
    closes = [100 + ((i * 37) % 11 - 5) * 0.5 + i * 0.05 for i in range(120)]
    bars = _bars(closes)
    calls = []
    def foresight(sym, hist):
        # k-th call == k-th bar (engine calls once per bar, in order).
        # hist[k+1] exists ONLY if the clamp leaked the future.
        k = len(calls)
        calls.append(1)
        if len(hist) > k + 1 and hist[k + 1].close > hist[k].close * 1.001:
            b = hist[k]
            return Signal(sym, "buy", b.close, atr=0.05, strategy="f", epoch=b.epoch)
        return None
    r_ok = bt.run_backtest(candles_by_symbol={"EURUSD": bars}, strategy=foresight,
                           costs_by_symbol={"EURUSD": COSTS}, starting_equity=10_000)
    assert r_ok.trades == [], "clamped engine: history-only foresight cannot trade"
    calls.clear()
    monkeypatch.setattr(bt, "_history_upto", lambda bars, i: bars)  # THE MUTATION
    r_mut = bt.run_backtest(candles_by_symbol={"EURUSD": bars}, strategy=foresight,
                            costs_by_symbol={"EURUSD": COSTS}, starting_equity=10_000)
    assert len(r_mut.trades) > 0, "mutant must let the foresight strategy trade"
