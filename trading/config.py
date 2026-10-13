"""Plain-code configuration. Risk limits live here so they are auditable.

Do NOT raise these limits to make a backtest pass. Any change must be
reviewed and re-tested out-of-sample.
"""
from dataclasses import dataclass

# Master kill switch. Live trading code must not exist until the user
# explicitly authorises it. Every order path checks this flag.
LIVE_TRADING_ENABLED: bool = False

# Deriv demo-only connection details (verified against Deriv docs 2026-10-13:
# https://developers.deriv.com/docs/intro/api-overview/ ,
# https://github.com/deriv-com/deriv-api).
# NOTE: network calls against Deriv have NOT been verified in this environment
# (no demo token / no network test run). The adapter is written from docs only.
DERIV_DEMO_WS_URL = "wss://ws.derivws.com/websockets/v3"
DERIV_TEST_APP_ID = "1089"  # documented testing app_id; register your own for real use


@dataclass(frozen=True)
class RiskLimits:
    risk_per_trade_pct: float = 1.0      # 1% risk per trade
    atr_stop_multiple: float = 2.0       # stop distance = 2 x ATR
    max_daily_loss_pct: float = 3.0      # halt trading for the day after -3%
    max_drawdown_pct: float = 10.0       # kill switch after -10% from peak
    max_position_notional_pct: float = 25.0  # single position <= 25% of equity
    max_portfolio_notional_pct: float = 100.0  # all open positions <= 100% of equity


@dataclass(frozen=True)
class CostAssumptions:
    """Must be applied in EVERY backtest. No zero-cost backtests allowed."""
    spread_pips: float = 1.5
    pip_value_per_unit: float = 0.0001   # price units per pip (FX default)
    slippage_pips: float = 0.5
    commission_per_unit: float = 0.0     # absolute price units per unit traded
    fee_flat: float = 0.0                # flat fee per trade in account currency


RISK_LIMITS = RiskLimits()
COSTS = CostAssumptions()
