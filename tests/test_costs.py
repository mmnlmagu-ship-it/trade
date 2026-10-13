import pytest
from trading.costs import apply_costs, validate_cost_assumptions

def test_buy_pays_up_sell_receives_less():
    b = apply_costs(quote_price=1.1000, side="buy", units=1000, spread_pips=2.0,
                    pip_value_per_unit=0.0001, slippage_pips=1.0)
    s = apply_costs(quote_price=1.1000, side="sell", units=1000, spread_pips=2.0,
                    pip_value_per_unit=0.0001, slippage_pips=1.0)
    assert b.fill_price > 1.1000 > s.fill_price
    assert b.total_cost > 0 and s.total_cost > 0

def test_zero_cost_backtest_blocked():
    with pytest.raises(ValueError):
        validate_cost_assumptions(spread_pips=0, slippage_pips=0,
                                  commission_per_unit=0, fee_flat=0)

def test_negative_costs_rejected():
    with pytest.raises(ValueError):
        apply_costs(quote_price=1.0, side="buy", units=1, spread_pips=-1)
    with pytest.raises(ValueError):
        apply_costs(quote_price=0, side="buy", units=1, spread_pips=1)
