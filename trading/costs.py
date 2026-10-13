"""Transaction costs. EVERY backtest/simulation must apply these.

No look-ahead: costs are a pure function of (price, units, side).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class FillCosts:
    fill_price: float       # price after spread + slippage
    spread_cost: float
    slippage_cost: float
    fee_cost: float
    total_cost: float
    swap_cost: float = 0.0


def apply_costs(
    *,
    quote_price: float,
    side: str,
    units: float,
    spread_pips: float,
    pip_value_per_unit: float = 0.0001,
    slippage_pips: float = 0.0,
    commission_per_unit: float = 0.0,
    fee_flat: float = 0.0,
) -> FillCosts:
    """Apply spread + slippage + fees to a market fill.

    Buyers pay up (price rises), sellers receive less (price falls).
    Raises ValueError on non-positive price/units or negative costs so a
    zero-cost backtest cannot silently pass.
    """
    if quote_price <= 0:
        raise ValueError("quote_price must be positive")
    if units <= 0:
        raise ValueError("units must be positive")
    if spread_pips < 0 or slippage_pips < 0 or commission_per_unit < 0 or fee_flat < 0:
        raise ValueError("costs cannot be negative")

    spread = spread_pips * pip_value_per_unit
    slippage = slippage_pips * pip_value_per_unit
    half_spread = spread / 2.0

    if side == "buy":
        fill_price = quote_price + half_spread + slippage
    elif side == "sell":
        fill_price = quote_price - half_spread - slippage
    else:
        raise ValueError(f"unknown side {side!r}")

    spread_cost = half_spread * units
    slippage_cost = slippage * units
    fee_cost = commission_per_unit * units + fee_flat
    return FillCosts(
        fill_price=fill_price,
        spread_cost=spread_cost,
        slippage_cost=slippage_cost,
        fee_cost=fee_cost,
        total_cost=spread_cost + slippage_cost + fee_cost,
    )


def validate_cost_assumptions(**kwargs) -> None:
    """Guard: a backtest must pass non-zero friction of some kind.

    At least one of spread/slippage/commission/fee must be > 0.
    """
    total = (
        kwargs.get("spread_pips", 0)
        + kwargs.get("slippage_pips", 0)
        + kwargs.get("commission_per_unit", 0)
        + kwargs.get("fee_flat", 0)
    )
    if total <= 0:
        raise ValueError(
            "Backtest blocked: spread+slippage+fees are all zero. "
            "Every backtest must include costs (see trading.config.COSTS)."
        )


def overnight_swap(
    *,
    units: float,
    side: str,
    nights: int,
    swap_long_per_unit_night: float = 0.0,
    swap_short_per_unit_night: float = 0.0,
    multiplier: float = 1.0,
) -> float:
    """Overnight financing charge for `nights` held, in account currency.

    Convention: negative swap value = cost to the trader, positive = rebate.
    Returns the signed P&L adjustment (usually <= 0). A round number of
    nights must be >= 0; weekends/holidays are the caller's `nights` count.
    """
    if units <= 0:
        raise ValueError("units must be positive")
    if nights < 0:
        raise ValueError("nights cannot be negative")
    if multiplier < 0:
        raise ValueError("multiplier cannot be negative")  # 0 = no rollover (closed weekend)
    if side == "buy":
        rate = swap_long_per_unit_night
    elif side == "sell":
        rate = swap_short_per_unit_night
    else:
        raise ValueError(f"unknown side {side!r}")
    return rate * units * nights * multiplier


def validate_backtest_costs(costs_by_symbol: dict) -> None:
    """Guard: EVERY symbol in a backtest must carry non-zero friction.

    Each entry must define spread/slippage/commission/fee with a combined
    total > 0, or swaps (long/short) != 0 counting as friction. Zero-cost
    symbols raise so a free-lunch backtest cannot silently pass.
    """
    if not costs_by_symbol:
        raise ValueError("Backtest blocked: no cost assumptions supplied.")
    for sym, c in costs_by_symbol.items():
        friction = (
            abs(c.get("spread_pips", 0))
            + abs(c.get("slippage_pips", 0))
            + abs(c.get("commission_per_unit", 0))
            + abs(c.get("fee_flat", 0))
            + abs(c.get("swap_long_per_unit_night", 0))
            + abs(c.get("swap_short_per_unit_night", 0))
            + abs(c.get("raw_long", 0))
            + abs(c.get("raw_short", 0))
        )
        if friction <= 0:
            raise ValueError(
                f"Backtest blocked: zero costs for {sym}. "
                "Every backtest must include spread/slippage/fees ( swaps count)."
            )
