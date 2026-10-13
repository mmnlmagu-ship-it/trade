"""Backtest engine (Stage 2, Deriv version). Daily bars.

Hard rules, enforced in code:
- as_of clamping: strategy sees only bars with epoch <= current bar epoch.
- next-bar-open fills: signal on bar i fills at bar i+1 open, never sooner.
- costs on EVERY fill: spread + slippage + fees (zero-cost symbols raise).
- swaps: each night held is charged (Fri->Mon counts actual calendar nights).
- gap-through-stop: bar opening beyond the stop fills at the open (worse),
  not at the stop.
- risk veto: every signal passes RiskEngine.evaluate; vetoes are logged.
- portfolio cap: total open notional bounded by max_portfolio_notional_pct.
- walk-forward splits carry an embargo gap so train never touches test.

No profitability claims are made here; use walk-forward out-of-sample
splits before believing any result.
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple
import datetime as _dt

from trading.config import RISK_LIMITS
from trading.costs import apply_costs, validate_backtest_costs
from trading.decision_logger import DecisionLogger
from trading.gaps import GapFlag, flag_gaps
from trading.risk_engine import RiskEngine
from trading.swaps import charge_for_range
from trading.types import Candle, Signal

Strategy = Callable[[str, List[Candle]], Optional[Signal]]
DAY = 86400


@dataclass
class Trade:
    symbol: str
    side: str
    units: float
    entry_epoch: int
    exit_epoch: int
    entry_price: float
    exit_price: float
    entry_costs: float
    exit_costs: float
    swap_total: float
    pnl: float  # net of ALL costs and swaps


@dataclass
class BacktestResult:
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[Tuple[int, float]] = field(default_factory=list)
    stats: Dict[str, float] = field(default_factory=dict)
    costs_total: float = 0.0
    swap_total: float = 0.0
    vetoed: int = 0
    gap_flags: List[GapFlag] = field(default_factory=list)


@dataclass
class _OpenPos:
    symbol: str
    side: str
    units: float
    entry_price: float
    entry_costs: float
    entry_epoch: int
    stop: Optional[float]
    take_profit: Optional[float]
    swap_acc: float = 0.0


def _history_upto(bars: List[Candle], i: int) -> List[Candle]:
    """Bars the strategy may see at bar i: closed bars only, nothing past i.

    Single seam for the as_of clamp AND its self-check. The mutation test
    replaces this with `lambda bars, i: bars` (full future visible) and
    must then observe the look-ahead test FAIL - proving the test actually
    guards the clamp.
    """
    out = bars[:i + 1]
    assert all(b.epoch <= bars[i].epoch for b in out), "as_of clamp violated"
    return out


COST_STRESS_LEVELS = (1.0, 1.5, 2.0)


def walk_forward_splits(
    n_bars: int, n_splits: int = 3, embargo_bars: int = 5, min_train_bars: int = 30
) -> List[Tuple[Tuple[int, int], Tuple[int, int]]]:
    """Expanding-window splits with embargo. Returns [((tr_s,tr_e),(te_s,te_e))].

    Test blocks partition the tail; train = everything before test minus
    embargo. No train/test overlap, ever.
    """
    if n_bars < min_train_bars + n_splits:
        raise ValueError("not enough bars for walk-forward splits")
    test_len = (n_bars - min_train_bars) // n_splits
    if test_len <= embargo_bars:
        raise ValueError("not enough bars: increase history or reduce splits")
    out = []
    test_start = n_bars - test_len * n_splits
    for k in range(n_splits):
        te_s = test_start + k * test_len
        te_e = te_s + test_len if k < n_splits - 1 else n_bars
        tr_e = te_s - embargo_bars
        if tr_e <= 0:
            raise ValueError("embargo eats training window")
        out.append(((0, tr_e), (te_s, te_e)))
    # structural guarantee, checked not trusted
    for (a, b), (c, d) in out:
        assert b <= c - 0 and b + embargo_bars <= c, "walk-forward overlap"
    return out


def _exit_ref(bar: Candle, pos: _OpenPos) -> Optional[Tuple[float, str]]:
    """Stop/TP check on one bar. Returns (exit_reference_price, reason) or None.

    Gap-through-stop: open beyond stop -> exit at open (slippage applied
    later by apply_costs). Same-bar stop+TP ambiguity resolves to the stop.
    """
    if pos.side == "buy":
        stop_hit = pos.stop is not None and bar.low <= pos.stop
        tp_hit = pos.take_profit is not None and bar.high >= pos.take_profit
        if stop_hit:
            # gap-through-stop: opened beyond the stop -> exit at the open
            ref = bar.open if bar.open <= pos.stop else pos.stop
            return ref, "stop"
        if tp_hit:
            ref = bar.open if bar.open >= pos.take_profit else pos.take_profit
            return ref, "take_profit"
    else:
        stop_hit = pos.stop is not None and bar.high >= pos.stop
        tp_hit = pos.take_profit is not None and bar.low <= pos.take_profit
        if stop_hit:
            ref = bar.open if bar.open >= pos.stop else pos.stop
            return ref, "stop"
        if tp_hit:
            ref = bar.open if bar.open <= pos.take_profit else pos.take_profit
            return ref, "take_profit"
    return None


def run_backtest(
    *,
    candles_by_symbol: Dict[str, List[Candle]],
    strategy: Strategy,
    costs_by_symbol: Dict[str, dict],
    swaps_by_symbol: Optional[Dict[str, dict]] = None,
    starting_equity: float = 10_000.0,
    risk: Optional[RiskEngine] = None,
    logger: Optional[DecisionLogger] = None,
    cost_stress: float = 1.0,
) -> BacktestResult:
    """Run a daily multi-symbol backtest. See module docstring for rules.

    cost_stress scales spread AND swaps (1.0, 1.5 or 2.0): a strategy must
    survive stressed costs, not just base-case costs.
    """
    if cost_stress not in COST_STRESS_LEVELS:
        raise ValueError(f"cost_stress must be one of {COST_STRESS_LEVELS}")
    if starting_equity <= 0:
        raise ValueError("starting_equity must be positive")
    validate_backtest_costs(costs_by_symbol)
    for sym in candles_by_symbol:
        if sym not in costs_by_symbol:
            raise ValueError(f"Backtest blocked: no costs for {sym}")
    swaps_by_symbol = swaps_by_symbol or {}
    risk = risk if risk is not None else RiskEngine()

    for sym, bars in candles_by_symbol.items():
        if any(bars[i].epoch >= bars[i + 1].epoch for i in range(len(bars) - 1)):
            raise ValueError(f"candles for {sym} not strictly ascending")

    res = BacktestResult()
    cash = starting_equity
    equity = starting_equity
    opens: Dict[str, _OpenPos] = {}
    pending: Dict[str, dict] = {}  # symbol -> {side,units,stop,tp,due_epoch}
    epochs = sorted({b.epoch for bars in candles_by_symbol.values() for b in bars})
    by_sym_epoch = {(s, b.epoch): b for s, bars in candles_by_symbol.items() for b in bars}
    prev_epoch: Optional[int] = None

    def day_of(epoch: int) -> str:
        return _dt.datetime.fromtimestamp(epoch, _dt.timezone.utc).date().isoformat()

    def open_notional(mark: Optional[Dict[str, float]] = None) -> float:
        tot = 0.0
        for s, p in opens.items():
            px = (mark or {}).get(s, p.entry_price)
            tot += p.units * px
        return tot

    for idx, epoch in enumerate(epochs):
        # 1. overnight swaps for positions held across the date roll.
        # Shared charge_for_range() also powers scripts/check_swap.py, so
        # the terminal cross-check and the engine agree by construction.
        if prev_epoch is not None:
            d_from = _dt.datetime.fromtimestamp(prev_epoch, _dt.timezone.utc).date()
            d_to = _dt.datetime.fromtimestamp(epoch, _dt.timezone.utc).date()
            for p in opens.values():
                sw = swaps_by_symbol.get(p.symbol, {})
                bar = by_sym_epoch.get((p.symbol, epoch))
                ref = bar.close if bar is not None else p.entry_price
                adj = charge_for_range(units=p.units, side=p.side,
                                       date_from=d_from, date_to=d_to, sw=sw,
                                       ref_price=ref, cost_stress=cost_stress)
                p.swap_acc += adj
                cash += adj
                res.swap_total += adj
        # 2. pending next-bar-open fills due at this bar's open
        for sym, bars in candles_by_symbol.items():
            bar = by_sym_epoch.get((sym, epoch))
            pend = pending.get(sym)
            if pend is not None and bar is not None and bar.epoch >= pend["due_epoch"]:
                c = costs_by_symbol[sym]
                fill = apply_costs(quote_price=bar.open, side=pend["side"],
                                   units=pend["units"],
                                   spread_pips=c.get("spread_pips", 0.0) * cost_stress,
                                   pip_value_per_unit=c.get("pip_value_per_unit", 0.0001),
                                   slippage_pips=c.get("slippage_pips", 0.0),
                                   commission_per_unit=c.get("commission_per_unit", 0.0),
                                   fee_flat=c.get("fee_flat", 0.0))
                if pend["kind"] == "open":
                    cash -= fill.total_cost
                    opens[sym] = _OpenPos(sym, pend["side"], pend["units"],
                                          fill.fill_price, fill.total_cost,
                                          bar.epoch, pend["stop"], pend["tp"])
                    if logger:
                        did = logger.log_decision(strategy=pend["strategy"], symbol=sym,
                                                  side=pend["side"], signal_price=pend["ref_price"],
                                                  units=pend["units"], allowed=True)
                        pend["decision_id"] = did
                else:  # close (reverse-signal exit)
                    pos = opens.pop(sym, None)
                    if pos is not None:
                        cash -= fill.total_cost
                        gross = (fill.fill_price - pos.entry_price) * pos.units \
                            if pos.side == "buy" else (pos.entry_price - fill.fill_price) * pos.units
                        pnl = gross - pos.entry_costs - fill.total_cost + pos.swap_acc
                        res.costs_total += pos.entry_costs + fill.total_cost
                        res.trades.append(Trade(sym, pos.side, pos.units, pos.entry_epoch,
                                                bar.epoch, pos.entry_price, fill.fill_price,
                                                pos.entry_costs, fill.total_cost, pos.swap_acc, pnl))
                        if logger and pend.get("decision_id"):
                            logger.log_outcome(decision_id=pend["decision_id"],
                                               fill_price=fill.fill_price, pnl=pnl,
                                               balance_after=cash + open_notional())
                del pending[sym]
        # 3. stop/TP exits on this bar (fills first, so same-bar stop-outs count)
        for sym, bars in candles_by_symbol.items():
            bar = by_sym_epoch.get((sym, epoch))
            pos = opens.get(sym)
            if bar is None or pos is None:
                continue
            hit = _exit_ref(bar, pos)
            if hit is None:
                continue
            ref, _reason = hit
            c = costs_by_symbol[sym]
            exit_side = "sell" if pos.side == "buy" else "buy"
            fill = apply_costs(quote_price=ref, side=exit_side, units=pos.units,
                               spread_pips=c.get("spread_pips", 0.0) * cost_stress,
                               pip_value_per_unit=c.get("pip_value_per_unit", 0.0001),
                               slippage_pips=c.get("slippage_pips", 0.0),
                               commission_per_unit=c.get("commission_per_unit", 0.0),
                               fee_flat=c.get("fee_flat", 0.0))
            opens.pop(sym)
            if pending.get(sym, {}).get("kind") == "open":
                del pending[sym]  # stop-out cancels nothing; pending already filled
            cash -= fill.total_cost
            gross = (fill.fill_price - pos.entry_price) * pos.units \
                if pos.side == "buy" else (pos.entry_price - fill.fill_price) * pos.units
            pnl = gross - pos.entry_costs - fill.total_cost + pos.swap_acc
            res.costs_total += pos.entry_costs + fill.total_cost
            res.trades.append(Trade(sym, pos.side, pos.units, pos.entry_epoch,
                                    bar.epoch, pos.entry_price, fill.fill_price,
                                    pos.entry_costs, fill.total_cost, pos.swap_acc, pnl))
        # 4. strategy on closed bars only; fills at NEXT bar open
        for sym, bars in candles_by_symbol.items():
            i = next((k for k, b in enumerate(bars) if b.epoch == epoch), None)
            if i is None:
                continue
            history = _history_upto(bars, i)  # as_of clamp: nothing past bar i
            sig = strategy(sym, history)
            if sig is None or sym in opens or sym in pending:
                continue
            if sig.epoch > epoch:
                res.vetoed += 1  # look-ahead violation: signal from the future
                if logger:
                    logger.log_decision(strategy=sig.strategy, symbol=sym, side=sig.side,
                                        signal_price=sig.price, units=0.0, allowed=False,
                                        veto_reason="signal epoch after as_of (look-ahead)")
                continue
            equity_now = cash + sum(
                (by_sym_epoch[(s, epoch)].close - p.entry_price) * p.units
                if p.side == "buy" else
                (p.entry_price - by_sym_epoch[(s, epoch)].close) * p.units
                for s, p in opens.items() if (s, epoch) in by_sym_epoch)
            risk.mark_equity(max(equity_now, 1e-9), day_of(epoch))
            veto = risk.evaluate(sig, equity=equity_now, day=day_of(epoch))
            if not veto.allowed:
                res.vetoed += 1
                if logger:
                    logger.log_decision(strategy=sig.strategy, symbol=sym, side=sig.side,
                                        signal_price=sig.price, units=0.0, allowed=False,
                                        veto_reason=veto.reason)
                continue
            cap = risk.limits.max_portfolio_notional_pct / 100.0 * equity_now
            committed = open_notional({s: by_sym_epoch[(s, epoch)].close for s in opens
                                       if (s, epoch) in by_sym_epoch})
            committed += sum(v["units"] * v["ref_price"] for v in pending.values()
                             if v.get("kind") == "open")
            if committed + veto.units * sig.price > cap:
                res.vetoed += 1
                if logger:
                    logger.log_decision(strategy=sig.strategy, symbol=sym, side=sig.side,
                                        signal_price=sig.price, units=veto.units, allowed=False,
                                        veto_reason="portfolio exposure cap")
                continue
            nxt = bars[i + 1] if i + 1 < len(bars) else None
            if nxt is None:
                continue  # no next bar: signal expires, never filled early
            # one net position per symbol: signals while open are ignored
            # (no silent reversals); the open position's stop/TP governs.
            pending[sym] = {"kind": "open", "side": sig.side, "units": veto.units,
                            "stop": veto.stop_loss, "tp": None, "due_epoch": nxt.epoch,
                            "ref_price": sig.price, "strategy": sig.strategy}
        # 5. mark equity at closes
        mtm = 0.0
        for sym, pos in opens.items():
            bar = by_sym_epoch.get((sym, epoch))
            if bar is None:
                continue
            mtm += (bar.close - pos.entry_price) * pos.units if pos.side == "buy" \
                else (pos.entry_price - bar.close) * pos.units
        equity = cash + mtm
        res.equity_curve.append((epoch, equity))
        prev_epoch = epoch

    # final liquidation: close anything still open at its last bar close
    for sym, pos in list(opens.items()):
        last = candles_by_symbol[sym][-1]
        c = costs_by_symbol[sym]
        exit_side = "sell" if pos.side == "buy" else "buy"
        fill = apply_costs(quote_price=last.close, side=exit_side, units=pos.units,
                           spread_pips=c.get("spread_pips", 0.0) * cost_stress,
                           pip_value_per_unit=c.get("pip_value_per_unit", 0.0001),
                           slippage_pips=c.get("slippage_pips", 0.0),
                           commission_per_unit=c.get("commission_per_unit", 0.0),
                           fee_flat=c.get("fee_flat", 0.0))
        cash -= fill.total_cost
        gross = (fill.fill_price - pos.entry_price) * pos.units \
            if pos.side == "buy" else (pos.entry_price - fill.fill_price) * pos.units
        pnl = gross - pos.entry_costs - fill.total_cost + pos.swap_acc
        res.costs_total += pos.entry_costs + fill.total_cost
        res.trades.append(Trade(sym, pos.side, pos.units, pos.entry_epoch,
                                last.epoch, pos.entry_price, fill.fill_price,
                                pos.entry_costs, fill.total_cost, pos.swap_acc, pnl))
    opens.clear()
    equity = cash  # flat: no open positions left
    if res.equity_curve:
        res.equity_curve[-1] = (res.equity_curve[-1][0], equity)

    res.gap_flags = flag_gaps(candles_by_symbol)
    rets = [e for _, e in res.equity_curve]
    peak, maxdd = rets[0] if rets else starting_equity, 0.0
    for e in rets:
        peak = max(peak, e)
        maxdd = max(maxdd, (peak - e) / peak * 100 if peak else 0)
    wins = sum(1 for t in res.trades if t.pnl > 0)
    res.stats = {
        "starting_equity": starting_equity, "ending_equity": equity,
        "return_pct": (equity / starting_equity - 1) * 100,
        "n_trades": float(len(res.trades)), "vetoed": float(res.vetoed),
        "win_rate_pct": (wins / len(res.trades) * 100) if res.trades else 0.0,
        "max_drawdown_pct": maxdd, "total_costs": res.costs_total,
        "total_swaps": res.swap_total,
        "cost_stress": cost_stress,
        "n_gap_flags": float(len(res.gap_flags)),
    }
    return res
