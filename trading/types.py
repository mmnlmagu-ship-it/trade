"""Shared value objects."""
from dataclasses import dataclass
from typing import Literal, Optional

Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class Candle:
    symbol: str
    timeframe: str
    epoch: int          # open time, unix seconds
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: Side
    # entry reference price at signal time (must be <= as_of candle close)
    price: float
    # ATR at signal time for volatility sizing; None => risk engine must reject
    atr: Optional[float] = None
    strategy: str = "unknown"
    epoch: int = 0


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: Side
    units: float
    # limit price if given; market order if None
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    tag: str = ""


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    symbol: str
    side: Side
    units: float
    fill_price: float
    # costs actually charged for this fill
    spread_cost: float
    slippage_cost: float
    fee_cost: float
    balance_after: float
