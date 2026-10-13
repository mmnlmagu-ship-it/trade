import datetime as dt
from trading.gaps import flag_gaps
from trading.types import Candle

def _bars(symbol, ohlc, start=2021):
    base = int(dt.datetime(start, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    return [Candle(symbol, "D1", base + i * 86400, o, h, l, c)
            for i, (o, h, l, c) in enumerate(ohlc)]

def test_big_gap_flagged():
    calm = [(100, 101, 99, 100.5)] * 20
    bars = _bars("EURUSD", calm + [(130, 131, 129, 130)])  # ~30 ATR gap
    flags = flag_gaps({"EURUSD": bars})
    assert len(flags) == 1 and flags[0].symbol == "EURUSD"
    assert flags[0].gap_atr > 5 and flags[0].epoch == bars[-1].epoch

def test_smooth_data_not_flagged():
    bars = _bars("EURUSD", [(100 + i * 0.1, 100 + i * 0.1 + 1, 100 + i * 0.1 - 1,
                             100 + i * 0.1 + 0.05) for i in range(30)])
    assert flag_gaps({"EURUSD": bars}) == []

def test_gaps_reported_in_backtest_result():
    from trading.backtest import run_backtest
    from trading.types import Signal
    calm = [(100, 101, 99, 100.5)] * 20
    bars = _bars("EURUSD", calm + [(130, 131, 129, 130), (130, 131, 129, 130)])
    COSTS = {"spread_pips": 1.5, "pip_value_per_unit": 0.01, "slippage_pips": 0.5}
    r = run_backtest(candles_by_symbol={"EURUSD": bars},
                     strategy=lambda s, h: None, costs_by_symbol={"EURUSD": COSTS})
    assert len(r.gap_flags) >= 1 and r.stats["n_gap_flags"] >= 1
