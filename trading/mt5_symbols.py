"""Deriv MT5 demo symbol map (Stage 2, Deriv version).

Your terminal's exact spelling wins: Deriv MT5 symbol names can carry
account/product suffixes (e.g. `.s`, `.a`) and descriptive labels differ
from compact tickers. This module maps whatever YOUR demo account shows
to 6 canonical keys used by the loader, data-check and backtest engine.

Canonical keys:
  EURUSD   - forex (Deriv product name: EURUSD)
  XAUUSD   - gold  (Deriv product name: XAUUSD)
  USOIL    - crude oil WTI (Deriv product name: US Oil)
  US30     - Dow (Deriv product name: Wall Street 30)
  US500    - S&P 500 (Deriv product name: US SP 500)
  USTEC    - Nasdaq 100 (Deriv product name: US Tech 100)

 researched 2026-10-13 from Deriv product pages:
  deriv.com/markets/forex, /markets/commodities/energies/oil,
  /markets/stock-indices/us-indices/{wall-street-30,us-tech-100},
  /trading-specifications. MT5 symbol search: Market Watch -> Symbols.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional

CANONICAL_SYMBOLS: List[str] = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
                                 "XAUUSD", "XAGUSD", "USOIL", "UKOIL",
                                 "US30", "US500", "USTEC"]

DERIV_PRODUCT_NAMES: Dict[str, str] = {
    "EURUSD": "EURUSD",
    "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY",
    "AUDUSD": "AUDUSD",
    "USDCAD": "USDCAD",
    "XAUUSD": "XAUUSD",
    "XAGUSD": "XAGUSD",
    "USOIL": "US Oil (WTI)",
    "UKOIL": "UK Brent Oil",
    "US30": "Wall Street 30",
    "US500": "US SP 500",
    "USTEC": "US Tech 100",
}

# Common spellings seen across Deriv MT5 servers / docs / third parties.
_ALIASES: Dict[str, str] = {
    "EURUSD": "EURUSD", "EURUSD.S": "EURUSD", "EURUSD.A": "EURUSD",
    "GBPUSD": "GBPUSD", "GBPUSD.S": "GBPUSD",
    "USDJPY": "USDJPY", "USDJPY.S": "USDJPY",
    "AUDUSD": "AUDUSD", "AUDUSD.S": "AUDUSD",
    "USDCAD": "USDCAD", "USDCAD.S": "USDCAD",
    "XAUUSD": "XAUUSD", "XAUUSD.S": "XAUUSD", "GOLD": "XAUUSD",
    "XAGUSD": "XAGUSD", "XAGUSD.S": "XAGUSD", "SILVER": "XAGUSD",
    "USOIL": "USOIL", "US OIL": "USOIL", "WTI": "USOIL", "USOIL.WTI": "USOIL",
    "UKOIL": "UKOIL", "UK BRENT OIL": "UKOIL", "BRENT": "UKOIL", "UKOIL.BRENT": "UKOIL",
    "US30": "US30", "WALL STREET 30": "US30", "WS30": "US30", "DJ30": "US30",
    "US500": "US500", "US SP 500": "US500", "SPX500": "US500", "SP500": "US500",
    "USTEC": "USTEC", "US TECH 100": "USTEC", "NAS100": "USTEC", "NASDAQ100": "USTEC",
    "UTEC": "USTEC",
}


def _norm(name: str) -> str:
    return " ".join(name.strip().upper().replace("_", " ").split())


def resolve_symbol(name: str) -> Optional[str]:
    """Map any known spelling to its canonical key. None if unknown."""
    key = _norm(name)
    if key in _ALIASES:
        return _ALIASES[key]
    # try stripping a trailing .X suffix account marker
    base = key.split(".")[0]
    return _ALIASES.get(base)


@dataclass(frozen=True)
class SymbolSpec:
    """Per-symbol execution terms. Fill from YOUR terminal:
    Market Watch -> right-click symbol -> Specification.
    Spreads are variable; swaps depend on account type (swap-free
    accounts charge admin fees instead - see Deriv swap-free terms).
    """
    canonical: str
    mt5_name_raw: str = ""       # exact spelling on YOUR demo account
    contract_size: float = 0.0
    spread: float = 0.0          # typical spread in PRICE units
    swap_long: float = 0.0       # overnight charge per unit per night (<0 = cost)
    swap_short: float = 0.0
    swap_mode: str = "points"    # informational only
    notes: str = ""


EMPTY_SPECS: Dict[str, SymbolSpec] = {c: SymbolSpec(canonical=c) for c in CANONICAL_SYMBOLS}
