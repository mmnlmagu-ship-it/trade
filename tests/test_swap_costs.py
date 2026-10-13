import pytest
from trading.costs import overnight_swap, validate_backtest_costs

def test_swap_buy_uses_long_rate():
    assert overnight_swap(units=1000, side="buy", nights=3,
                          swap_long_per_unit_night=-0.01,
                          swap_short_per_unit_night=-0.02) == pytest.approx(-30.0)

def test_swap_short_and_weekend_nights():
    assert overnight_swap(units=100, side="sell", nights=3,
                          swap_short_per_unit_night=-0.05) == pytest.approx(-15.0)

def test_swap_rebate_positive():
    assert overnight_swap(units=10, side="buy", nights=1,
                          swap_long_per_unit_night=0.02) == pytest.approx(0.2)

def test_swap_negative_nights_rejected():
    with pytest.raises(ValueError):
        overnight_swap(units=1, side="buy", nights=-1)

def test_zero_cost_symbol_blocked_even_without_swaps():
    with pytest.raises(ValueError):
        validate_backtest_costs({"EURUSD": {}})

def test_swaps_count_as_friction():
    validate_backtest_costs({"XAUUSD": {"swap_long_per_unit_night": -0.01}})  # must not raise
