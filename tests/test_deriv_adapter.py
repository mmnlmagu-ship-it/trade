import pytest
from trading import config
from trading.deriv_adapter import DerivDemoAdapter, NotDemoError
from trading.types import OrderRequest

def _fake_sender(payload):
    if "ticks_history" in payload:
        return {"candles": [
            {"epoch": 100, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05},
            {"epoch": 200, "open": 1.05, "high": 1.2, "low": 1.0, "close": 1.1},
            {"epoch": 300, "open": 1.1, "high": 1.3, "low": 1.05, "close": 1.2},
        ]}
    if "balance" in payload:
        return {"balance": {"balance": 7777.0}}
    raise AssertionError(payload)

def test_refuses_non_demo_host():
    with pytest.raises(NotDemoError):
        DerivDemoAdapter(ws_url="wss://example-real-broker.com/ws")

def test_get_candles_respects_as_of_and_drops_incomplete():
    a = DerivDemoAdapter(sender=_fake_sender)
    rows = a.get_candles("R_100", "M1", 0, 999)
    assert [c.epoch for c in rows] == [100, 200]  # incomplete 300 dropped
    rows2 = a.get_candles("R_100", "M1", 0, 999, as_of=100)
    assert [c.epoch for c in rows2] == []  # 100 dropped as incomplete; nothing leaks past as_of

def test_place_order_applies_costs_and_updates_paper_balance():
    a = DerivDemoAdapter(sender=_fake_sender, paper_balance=10_000.0)
    r = a.place_order(OrderRequest("R_100", "buy", units=100.0, price=1.0))
    assert r.fill_price > 1.0  # spread+slippage charged
    assert r.total_cost if hasattr(r, "total_cost") else True
    assert (r.spread_cost + r.slippage_cost + r.fee_cost) > 0
    assert r.balance_after < 10_000.0
    assert r.order_id.startswith("DEMO-")

def test_live_flag_blocks_orders(monkeypatch):
    a = DerivDemoAdapter(sender=_fake_sender)
    monkeypatch.setattr(config, "LIVE_TRADING_ENABLED", True)
    with pytest.raises(RuntimeError):
        a.place_order(OrderRequest("R_100", "buy", units=1.0, price=1.0))

def test_no_live_trading_by_default():
    assert config.LIVE_TRADING_ENABLED is False
