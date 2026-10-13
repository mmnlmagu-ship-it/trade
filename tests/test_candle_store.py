from trading.candle_store import CandleStore
from trading.types import Candle

def _mk(epoch, close):
    return Candle("EURUSD", "H1", epoch, 1.0, 1.1, 0.9, close)

def test_save_and_clamp_as_of():
    s = CandleStore()
    s.save_candles([_mk(100, 1.0), _mk(200, 2.0), _mk(300, 3.0)])
    rows = s.get_candles("EURUSD", "H1", as_of=200)
    assert [c.epoch for c in rows] == [100, 200]
    rows2 = s.get_candles("EURUSD", "H1", start=0, end=9999, as_of=150)
    assert [c.epoch for c in rows2] == [100]
    s.close()

def test_empty_store_returns_empty():
    s = CandleStore()
    assert s.get_candles("X", "H1", as_of=999) == []
    assert s.get_latest_closed("X", "H1", as_of=999) is None
    s.close()
