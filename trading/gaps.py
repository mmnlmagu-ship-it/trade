"""Gap review flags: daily bars gapping over 5 ATR need human eyes.

A gap here means the open printed far from the prior close - exactly the
bars where stop-fill modelling is weakest (gap-through-stop is an
estimate, not a traded price). Flagged bars don't block the backtest;
they are reported for manual review.
"""
from dataclasses import dataclass
from typing import Dict, List
from trading.types import Candle


@dataclass(frozen=True)
class GapFlag:
    symbol: str
    epoch: int
    gap: float          # open - prev_close, price units
    gap_atr: float      # gap in multiples of trailing ATR
    atr: float


def _true_range(prev_close: float, bar: Candle) -> float:
    return max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close))


def flag_gaps(candles_by_symbol: Dict[str, List[Candle]],
              atr_window: int = 14, threshold_atr: float = 5.0) -> List[GapFlag]:
    out: List[GapFlag] = []
    for sym, bars in candles_by_symbol.items():
        if len(bars) < atr_window + 1:
            continue
        trs = [bars[0].high - bars[0].low]
        for i in range(1, len(bars)):
            trs.append(_true_range(bars[i - 1].close, bars[i]))
        for i in range(atr_window, len(bars)):
            atr = sum(trs[i - atr_window + 1:i + 1]) / atr_window
            if atr <= 0:
                continue
            gap = bars[i].open - bars[i - 1].close
            if abs(gap) > threshold_atr * atr:
                out.append(GapFlag(sym, bars[i].epoch, gap, gap / atr, atr))
    return out
