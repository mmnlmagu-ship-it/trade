"""Cross-cutting: nothing may return data past as_of."""
from trading.candle_store import CandleStore
from trading.deriv_adapter import DerivDemoAdapter
from trading.types import Candle

def test_store_and_adapter_never_leak_future():
    s = CandleStore()
    s.save_candles([Candle("S", "H1", e, 1, 1, 1, 1) for e in (10, 20, 30)])
    assert max(c.epoch for c in s.get_candles("S", "H1", start=0, end=10_000, as_of=20)) <= 20

    def sender(p):
        return {"candles": [{"epoch": e, "open": 1, "high": 1, "low": 1, "close": 1}
                            for e in (10, 20, 30, 9_999)]}
    a = DerivDemoAdapter(sender=sender)
    got = a.get_candles("S", "M1", 0, 10_000, as_of=20)
    assert got and max(c.epoch for c in got) <= 20
    s.close()
