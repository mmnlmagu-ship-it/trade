"""Risk engine. Plain code, vetoes any signal.

Limits (defaults from trading.config.RISK_LIMITS):
- 1% risk per trade (volatility-based sizing via ATR stop)
- max daily loss halt
- max drawdown kill switch (manual reset required)
"""
from dataclasses import dataclass, field
from typing import Optional
from trading.config import RISK_LIMITS, RiskLimits
from trading.types import Signal


@dataclass
class Veto:
    allowed: bool
    reason: str = ""
    units: float = 0.0
    stop_loss: Optional[float] = None


@dataclass
class RiskEngine:
    limits: RiskLimits = field(default_factory=lambda: RISK_LIMITS)
    peak_equity: Optional[float] = None
    day_start_equity: Optional[float] = None
    current_day: Optional[str] = None
    halted_day: Optional[str] = None
    kill_switch_tripped: bool = False

    def mark_equity(self, equity: float, day: str) -> None:
        """Feed equity curve; enforces daily-loss halt and drawdown kill switch."""
        if equity <= 0:
            raise ValueError("equity must be positive")
        if self.peak_equity is None or equity > self.peak_equity:
            self.peak_equity = equity
        if self.current_day != day:
            self.current_day = day
            self.day_start_equity = equity
        assert self.peak_equity is not None and self.day_start_equity is not None
        # Max drawdown kill switch (latching: requires manual reset)
        dd_pct = (self.peak_equity - equity) / self.peak_equity * 100.0
        if dd_pct >= self.limits.max_drawdown_pct:
            self.kill_switch_tripped = True
        # Max daily loss halt (resets on new day)
        day_loss_pct = (self.day_start_equity - equity) / self.day_start_equity * 100.0
        if day_loss_pct >= self.limits.max_daily_loss_pct:
            self.halted_day = day

    def reset_kill_switch(self) -> None:
        """Manual reset only. There is deliberately no automatic reset."""
        self.kill_switch_tripped = False
        self.halted_day = None

    def position_size(self, *, equity: float, atr: float) -> float:
        """Volatility-based sizing: risk_amount / (ATR * stop_multiple)."""
        if equity <= 0:
            raise ValueError("equity must be positive")
        if atr is None or atr <= 0:
            raise ValueError("ATR must be positive for volatility sizing")
        risk_amount = equity * self.limits.risk_per_trade_pct / 100.0
        stop_distance = atr * self.limits.atr_stop_multiple
        units = risk_amount / stop_distance
        max_notional = equity * self.limits.max_position_notional_pct / 100.0
        # NOTE: capping by notional needs a price; the caller enforces it in
        # evaluate() where signal.price is known. This raw unit value is uncapped.
        return units

    def evaluate(self, signal: Signal, *, equity: float, day: str) -> Veto:
        """Veto any signal. Returns allowed=False with reason if blocked."""
        if self.kill_switch_tripped:
            return Veto(False, "kill switch tripped (max drawdown); manual reset required")
        if self.halted_day == day:
            return Veto(False, f"max daily loss reached for {day}")
        if equity <= 0:
            return Veto(False, "equity must be positive")
        if signal.atr is None or signal.atr <= 0:
            return Veto(False, "missing/invalid ATR: volatility sizing impossible")
        if signal.price is None or signal.price <= 0:
            return Veto(False, "missing/invalid signal price")
        try:
            units = self.position_size(equity=equity, atr=signal.atr)
        except ValueError as e:
            return Veto(False, str(e))
        notional = units * signal.price
        max_notional = equity * self.limits.max_position_notional_pct / 100.0
        if notional > max_notional:
            units = max_notional / signal.price
            notional = max_notional
        if units <= 0:
            return Veto(False, "sized to zero units")
        stop_distance = signal.atr * self.limits.atr_stop_multiple
        stop = signal.price - stop_distance if signal.side == "buy" else signal.price + stop_distance
        return Veto(True, "", units, stop)
