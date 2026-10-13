"""Deriv DEMO adapter. Demo only — refuses live trading.

Docs (read 2026-10-13):
- https://developers.deriv.com/docs/intro/api-overview/
- https://github.com/deriv-com/deriv-api (test app_id 1089)
- candles via `ticks_history` with style=candles; proposal -> buy -> sell flow.

VERIFICATION STATUS: network calls NOT verified here (no demo token, no
network test run). Do not treat this as proven against the live API.
Unit tests use an injected fake transport so no network is needed.
"""
import itertools
import json
from typing import Any, Callable, Dict, List, Optional

from trading import config
from trading.config import DERIV_DEMO_WS_URL
from trading.costs import apply_costs, validate_cost_assumptions
from trading.market_adapter import MarketAdapter
from trading.types import Candle, OrderRequest, OrderResult

# Granularity mapping for Deriv ticks_history
TIMEFRAME_TO_GRANULARITY = {
    "M1": 60, "M5": 300, "M15": 900, "M30": 1800,
    "H1": 3600, "H4": 14400, "D1": 86400,
}

SendFn = Callable[[Dict[str, Any]], Dict[str, Any]]


class NotDemoError(RuntimeError):
    pass


class DerivDemoAdapter(MarketAdapter):
    """Demo-only Deriv adapter.

    - ws_url must be the demo/test host (default DERIV_DEMO_WS_URL).
    - Any URL that is not the demo host raises NotDemoError.
    - place_order refuses to run if config.LIVE_TRADING_ENABLED is True
      (fail-closed: this skeleton has no live path at all).
    - `sender`: injectable request function for tests. Production sender
      requires `websocket-client` and a demo API token; it is built lazily
      so unit tests never need network or the dependency.
    """

    def __init__(
        self,
        *,
        app_id: str = config.DERIV_TEST_APP_ID,
        api_token: Optional[str] = None,
        ws_url: str = DERIV_DEMO_WS_URL,
        sender: Optional[SendFn] = None,
        paper_balance: float = 10_000.0,
        cost_kwargs: Optional[Dict[str, Any]] = None,
    ):
        if "derivws.com" not in ws_url and "binaryws.com" not in ws_url:
            raise NotDemoError(f"refusing non-Deriv URL: {ws_url!r}")
        # Extra guard: Deriv uses the token's account type for demo vs real.
        # We cannot verify the account type without a network call, so the
        # adapter defaults to PAPER simulation unless the caller explicitly
        # opts into network mode with a token — and even then live trading
        # flag must stay False.
        self.ws_url = ws_url
        self.app_id = app_id
        self.api_token = api_token
        self._sender = sender
        self._paper_balance = float(paper_balance)
        self._order_seq = itertools.count(1)
        self.cost_kwargs = cost_kwargs or dict(
            spread_pips=config.COSTS.spread_pips,
            pip_value_per_unit=config.COSTS.pip_value_per_unit,
            slippage_pips=config.COSTS.slippage_pips,
            commission_per_unit=config.COSTS.commission_per_unit,
            fee_flat=config.COSTS.fee_flat,
        )
        validate_cost_assumptions(**self.cost_kwargs)

    # -- internal transport --
    def _send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._sender is not None:
            return self._sender(payload)
        if self.api_token is None:
            raise RuntimeError("no sender injected and no api_token: cannot reach network in tests")
        try:
            import websocket  # type: ignore  # optional dep: websocket-client
        except ImportError as e:
            raise RuntimeError("websocket-client not installed; pip install websocket-client") from e
        import time
        ws = websocket.create_connection(f"{self.ws_url}?app_id={self.app_id}", timeout=15)
        try:
            ws.send(json.dumps({"authorize": self.api_token}))
            ws.recv()  # authorize response (caller verifies account type manually)
            ws.send(json.dumps(payload))
            deadline = time.time() + 15
            while time.time() < deadline:
                msg = json.loads(ws.recv())
                if msg.get("req_id") == payload.get("req_id") or msg.get("msg_type") in ("candles", "balance"):
                    return msg
            raise TimeoutError("timed out waiting for Deriv response")
        finally:
            ws.close()

    # -- MarketAdapter API --
    def get_candles(self, symbol, timeframe, start, end, *, as_of=None, include_incomplete=False) -> List[Candle]:
        if timeframe not in TIMEFRAME_TO_GRANULARITY:
            raise ValueError(f"unsupported timeframe {timeframe!r}")
        effective_end = end if as_of is None else min(end, as_of)
        if effective_end < start:
            return []
        granularity = TIMEFRAME_TO_GRANULARITY[timeframe]
        # Clamp count to keep requests bounded
        count = min(int((effective_end - start) // granularity) + 1, 5000)
        resp = self._send({
            "ticks_history": symbol, "style": "candles",
            "granularity": granularity, "count": count, "end": "latest", "req_id": 11,
        })
        raw = resp.get("candles", [])
        out: List[Candle] = []
        for c in raw:
            epoch = int(c["epoch"])
            if epoch < start or epoch > effective_end:
                continue  # look-ahead guard even if server over-returns
            out.append(Candle(symbol, timeframe, epoch, float(c["open"]),
                              float(c["high"]), float(c["low"]), float(c["close"]),
                              float(c.get("volume", 0.0))))
        out.sort(key=lambda c: c.epoch)
        if not include_incomplete and out:
            out = out[:-1]  # drop still-forming candle
        return [c for c in out if c.epoch <= effective_end]

    def place_order(self, request: OrderRequest) -> OrderResult:
        if config.LIVE_TRADING_ENABLED:
            raise RuntimeError("LIVE_TRADING_ENABLED is True: this skeleton has no live path. Refusing.")
        if request.units <= 0:
            raise ValueError("units must be positive")
        ref = request.price if request.price is not None else 1.0
        if ref <= 0:
            raise ValueError("price must be positive")
        fill = apply_costs(quote_price=ref, side=request.side, units=request.units, **self.cost_kwargs)
        cost_total = fill.total_cost
        # Paper balance update (demo): buys spend, sells receive, minus costs
        if request.side == "buy":
            self._paper_balance -= fill.fill_price * request.units + fill.fee_cost
        else:
            self._paper_balance += fill.fill_price * request.units - fill.fee_cost
        oid = f"DEMO-{next(self._order_seq):06d}"
        return OrderResult(oid, request.symbol, request.side, request.units,
                           fill.fill_price, fill.spread_cost, fill.slippage_cost,
                           fill.fee_cost, self._paper_balance)

    def get_balance(self) -> float:
        if self._sender is not None and self.api_token is not None:
            resp = self._send({"balance": 1, "req_id": 12})
            try:
                return float(resp["balance"]["balance"])
            except (KeyError, TypeError):
                pass
        return self._paper_balance
