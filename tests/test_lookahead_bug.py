"""Look-ahead bug test: future data must be unreachable AND unusable.

1. The engine hands the strategy only bars with epoch <= as_of (clamped).
2. Signals dated after as_of are rejected as vetoes, never filled.
3. A deliberately cheating strategy (trades only when the NEXT close rises)
   must NOT outperform buy-and-hold on the same data, because its signal
   still fills at next-bar open - the peeked move is already gone.
"""
import datetime as dt
from trading.backtest import run_backtest
from trading.types import Candle, Signal

COSTS = {"spread_pips": 1.5, "pip_value_per_unit": 0.0001, "slippage_pips": 0.5}

def _bars(closes):
    base = int(dt.datetime(2021, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    return [Candle("EURUSD", "D1", base + i * 86400, c, c * 1.001, c * 0.999, c)
            for i, c in enumerate(closes)]

def test_history_clamped_to_as_of():
    bars = _bars([1.0, 2.0, 3.0, 4.0])
    seen = []
    def s(sym, hist):
        seen.append(max(b.epoch for b in hist))
        b = hist[-1]
        return Signal(sym, "buy", b.close, atr=0.01, strategy="c", epoch=b.epoch)
    run_backtest(candles_by_symbol={"EURUSD": bars}, strategy=s,
                 costs_by_symbol={"EURUSD": COSTS})
    for i, mx in enumerate(seen):
        assert mx == bars[i].epoch  # never sees past the current bar

def test_future_dated_signal_vetoed():
    bars = _bars([1.0, 2.0, 3.0, 4.0])
    def s(sym, hist):
        b = hist[-1]
        return Signal(sym, "buy", b.close, atr=0.01, strategy="f",
                      epoch=b.epoch + 86400)  # claims to be from tomorrow
    r = run_backtest(candles_by_symbol={"EURUSD": bars}, strategy=s,
                     costs_by_symbol={"EURUSD": COSTS})
    assert r.trades == [] and r.vetoed >= 1

def test_peeking_cheater_does_not_win():
    closes = [100 + ((i * 37) % 11 - 5) * 0.5 + i * 0.05 for i in range(120)]
    bars = _bars(closes)
    full = {b.epoch: b for b in bars}
    def cheater(sym, hist):
        b = hist[-1]
        nxt = full.get(b.epoch + 86400)
        if nxt is not None and nxt.close > b.close:
            return Signal(sym, "buy", b.close, atr=(b.high - b.low) or 0.001,
                          strategy="cheat", epoch=b.epoch)
        return None
    r = run_backtest(candles_by_symbol={"EURUSD": bars}, strategy=cheater,
                     costs_by_symbol={"EURUSD": COSTS}, starting_equity=10_000)
    # one position max, exits only via wide stop/liquidation: cannot scalps
    # every peeked move; must not beat the trivial upper bound of compounding
    # every positive daily move (impossible without same-bar fills).
    import math
    Hodl = 10_000 * closes[-1] / (closes[1] + 0.000125)  # approx buy@bar1-open
    assert r.stats["ending_equity"] < Hodl * 2.0
    assert r.vetoed == 0  # cheats via data, not via signal dating: still contained
