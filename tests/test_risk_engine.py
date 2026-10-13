from trading.risk_engine import RiskEngine
from trading.config import RiskLimits
from trading.types import Signal

def test_one_percent_volatility_sizing():
    eng = RiskEngine(limits=RiskLimits(risk_per_trade_pct=1.0, atr_stop_multiple=2.0,
                                       max_daily_loss_pct=3.0, max_drawdown_pct=10.0,
                                       max_position_notional_pct=1000.0))
    v = eng.evaluate(Signal("EURUSD", "buy", 1.1000, atr=0.0020), equity=10_000, day="2026-01-01")
    assert v.allowed
    # risk $100 / (2*0.002) = 25000 units
    assert abs(v.units - 25_000) < 1e-6
    assert abs(v.stop_loss - (1.1000 - 0.004)) < 1e-9

def test_missing_atr_rejected():
    eng = RiskEngine()
    v = eng.evaluate(Signal("EURUSD", "buy", 1.1, atr=None), equity=10_000, day="d1")
    assert not v.allowed and "ATR" in v.reason

def test_daily_loss_halt():
    eng = RiskEngine()
    eng.mark_equity(10_000, "d1")
    eng.mark_equity(9_600, "d1")  # -4% > 3% limit
    v = eng.evaluate(Signal("EURUSD", "buy", 1.1, atr=0.001), equity=9_600, day="d1")
    assert not v.allowed and "daily loss" in v.reason
    # new day resets the halt
    v2 = eng.evaluate(Signal("EURUSD", "buy", 1.1, atr=0.001), equity=9_600, day="d2")
    assert v2.allowed

def test_drawdown_kill_switch_latches():
    eng = RiskEngine()
    eng.mark_equity(10_000, "d1")
    eng.mark_equity(8_900, "d2")  # -11% > 10% limit
    assert eng.kill_switch_tripped
    v = eng.evaluate(Signal("EURUSD", "buy", 1.1, atr=0.001), equity=8_900, day="d3")
    assert not v.allowed and "kill switch" in v.reason
    eng.reset_kill_switch()
    v2 = eng.evaluate(Signal("EURUSD", "buy", 1.1, atr=0.001), equity=8_900, day="d3")
    assert v2.allowed
