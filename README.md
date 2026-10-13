# Trading system — Stage 1 skeleton

Rules: no look-ahead bias · every backtest includes spread+slippage+fees ·
risk limits in plain code with veto · **no live trading until authorised**.

`trading/config.py::LIVE_TRADING_ENABLED` is `False`. `DerivDemoAdapter`
refuses non-demo hosts and raises if the live flag is ever `True`.

## Layout
- `trading/market_adapter.py` — interface (`get_candles`, `place_order`, `get_balance`)
- `trading/deriv_adapter.py` — Deriv **demo** adapter (docs-based, network UNVERIFIED)
- `trading/candle_store.py` — SQLite candle store, `as_of` clamps reads
- `trading/decision_logger.py` — append-only decision/outcome log
- `trading/risk_engine.py` — 1%/trade, ATR sizing, daily-loss halt, drawdown kill switch
- `trading/costs.py` — spread/slippage/fees; zero-cost backtests raise
- `tests/` — unit tests (`pip install -r requirements.txt && python -m pytest -q`)

## Verification status (honest)
- Unit-tested: store, logger, risk, costs, adapter paper path, look-ahead guards.
- NOT verified: real Deriv network calls (no demo token / no network run here).
  Before any demo run you must supply `app_id` + demo `api_token` and confirm
  the authorised account is a demo account.
- No profitability claims: no strategy, no backtest results yet by design.

## Stage 2 (Deriv version)
- `trading/mt5_symbols.py` - 6 canonical symbols (EURUSD, XAUUSD, USOIL/WTI,
  US30, US500, USTEC) + alias resolution for YOUR demo's exact spellings.
- `trading/csv_loader.py` - daily CSV source (MT5 D1 Ctrl+S exports).
  MT5 is NOT reachable from this Linux VM (needs Windows terminal), so CSV
  is the data path until you export from your own machine.
- `scripts/data_check.py` - reports years/bars + spread/swap per symbol;
  exits 1 unless all 6 load. Specs template: `specs/specs_template.csv`
  (fill spread/swap from Market Watch -> Specification on YOUR demo).
- `trading/backtest.py` - as_of-clamped history, next-bar-open fills,
  gap-through-stop at the open, spread/slippage/fees + per-night swaps
  (Fri->Mon = 3 nights), risk-engine veto on every signal, portfolio cap
  incl. pending fills, final-bar liquidation, embargoed walk-forward splits.
- Tests: `python -m pytest -q` (45 tests, incl. a look-ahead bug test where
  a peeking cheater strategy is contained by next-bar-open mechanics).

## Pre-strategy hardening
- `trading/swaps.py` - MT5 swap-mode conversion (POINTS / per-lot currency /
  interest / reopen) to account-ccy per unit per night + per-night triple-swap
  weekday multipliers (MT5 0=Sunday..6=Saturday; terminal value wins).
- Exporter refuses non-demo accounts (`check_demo_account`: trade_mode must be
  demo AND server name must contain "demo"); exports raw swap rates + mode +
  triple weekday per symbol.
- 12 symbols: EURUSD GBPUSD USDJPY AUDUSD USDCAD XAUUSD XAGUSD USOIL WTI
  UKOIL Brent US30 US500 USTEC.
- Backtester `cost_stress` (1.0/1.5/2.0) scales spread AND swaps; recorded in stats.
- Mutation test (`test_mutation_asof.py`) disables the as_of clamp and proves
  the look-ahead guards fail without it.
- `trading/gaps.py`: bars gapping over 5 ATR are flagged in results and in
  `data_check.py` output for manual review.

## Swap hardening
- Weekends carry 0x rollover (market closed; weekend cost lives in the triple
  day). Monday-open to next-Monday-open = exactly 7 nights for both
  Wednesday- and Friday-triple symbols (test_swap_week.py pins this; the old
  calendar-night counting overcharged 9).
- Swap modes use named constants (SWAP_MODE_POINTS etc., mirroring
  mt5.SYMBOL_SWAP_MODE_*); the exporter prefers the package constants when
  exposed and self-checks the map on your machine. specs.csv stores
  swap_mode_name alongside the integer.
- scripts/check_swap.py replays the engine's own charge_for_range() against a
  terminal reading: `check_swap.py --specs specs/specs.csv --symbol XAUUSD
  --side buy --lots 1.5 --nights 3 --from 2021-01-04 --observed -12.40`.
