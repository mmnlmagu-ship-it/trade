import pytest
from trading.decision_logger import DecisionLogger

def test_decision_and_outcome_roundtrip():
    lg = DecisionLogger()
    did = lg.log_decision(strategy="s", symbol="EURUSD", side="buy",
                          signal_price=1.1, units=100, allowed=True)
    oid = lg.log_outcome(decision_id=did, fill_price=1.101, pnl=5.0, balance_after=10005)
    assert lg.count_decisions() == 1 and lg.count_outcomes() == 1
    lg.close()

def test_vetoed_decision_still_logged():
    lg = DecisionLogger()
    did = lg.log_decision(strategy="s", symbol="X", side="sell", signal_price=1.0,
                          units=0, allowed=False, veto_reason="kill switch tripped")
    assert lg.count_decisions() == 1
    lg.close()

def test_outcome_requires_decision():
    lg = DecisionLogger()
    with pytest.raises(ValueError):
        lg.log_outcome(decision_id="nope", fill_price=1.0, pnl=0, balance_after=0)
    lg.close()
