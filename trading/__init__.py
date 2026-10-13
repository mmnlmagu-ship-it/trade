"""Automated trading system — Stage 1 skeleton.

Rules (enforced in code, not just docs):
1. No look-ahead bias: candle reads are always bounded by as_of.
2. Every backtest must apply spread + slippage + fees (see trading.costs).
3. All risk limits live in trading.risk_engine and can veto any signal.
4. No live trading: trading.config.LIVE_TRADING_ENABLED is False and
   DerivDemoAdapter refuses to run against real-money endpoints.
"""
from trading.config import LIVE_TRADING_ENABLED

__all__ = ["LIVE_TRADING_ENABLED"]
