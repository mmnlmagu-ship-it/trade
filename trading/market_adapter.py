"""Market adapter interface."""
from abc import ABC, abstractmethod
from typing import List, Optional
from trading.types import Candle, OrderRequest, OrderResult


class MarketAdapter(ABC):
    """Exchange/broker interface. All adapters must implement this.

    Look-ahead rule: get_candles MUST only return candles with
    epoch <= as_of when as_of is given, and must never return the
    still-forming (unclosed) candle unless include_incomplete=True.
    """

    @abstractmethod
    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
        *,
        as_of: Optional[int] = None,
        include_incomplete: bool = False,
    ) -> List[Candle]:
        raise NotImplementedError

    @abstractmethod
    def place_order(self, request: OrderRequest) -> OrderResult:
        raise NotImplementedError

    @abstractmethod
    def get_balance(self) -> float:
        raise NotImplementedError
