"""Exporter helpers, tested with a fake mt5 module (no Windows needed)."""
import csv
import importlib.util
import sys
import types

def _load_exporter():
    spec = importlib.util.spec_from_file_location("mt5_export", "scripts/mt5_export.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

class _Sym:
    def __init__(self, name): self.name = name

class _Info:
    trade_contract_size = 100
    spread = 12
    point = 0.00001
    swap_long = -0.5
    swap_short = -0.3
    swap_mode = 1
    swap_rollover3days = 3
    trade_tick_size = 0.00001
    digits = 5
    tick_value = 1.0

class _Acct:
    def __init__(self, login=12345, server="Deriv-Demo", trade_mode=2):
        self.login = login; self.server = server; self.trade_mode = trade_mode

def _fake_mt5(names, n_rates=10):
    m = types.SimpleNamespace()
    m.TIMEFRAME_D1 = 16408
    m.symbols_get = lambda: [_Sym(n) for n in names]
    m.symbol_select = lambda s, b: True
    m.last_error = lambda: (0, "ok")
    m.shutdown = lambda: None
    import datetime
    base = int(datetime.datetime(2020, 1, 1).timestamp())
    m.copy_rates_from_pos = lambda s, tf, pos, cnt: [
        {"time": base + i * 86400, "open": 1.0, "high": 1.1, "low": 0.9,
         "close": 1.05, "tick_volume": 5, "real_volume": 0, "spread": 10}
        for i in range(n_rates)]
    m.symbol_info = lambda s: _Info()
    m.account_info = lambda: _Acct()
    m.ACCOUNT_TRADE_MODE_DEMO = 2
    return m

NAMES12 = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "XAUUSD", "XAGUSD",
           "US Oil", "UK Brent Oil", "Wall Street 30", "US SP 500", "US Tech 100"]

def test_discover_matches_all_twelve(tmp_path):
    mod = _load_exporter()
    found = mod.discover(mt5 := _fake_mt5(NAMES12), mod.CANDIDATES)
    assert len(found) == 12 and found["UKOIL"] == "UK Brent Oil"
    assert found["USOIL"] == "US Oil" and found["XAGUSD"] == "XAGUSD"

def test_discover_exits_when_symbol_absent():
    mod = _load_exporter()
    mt5 = _fake_mt5(["EURUSD"])
    try:
        mod.discover(mt5, mod.CANDIDATES)
    except SystemExit as e:
        assert "GBPUSD" in str(e)
    else:
        raise AssertionError("should have exited")

def test_demo_check_passes_on_deriv_demo():
    mod = _load_exporter()
    assert mod.check_demo_account(_fake_mt5(NAMES12)) == (12345, "Deriv-Demo")

def test_demo_check_refuses_real_account():
    import pytest as _pt
    mod = _load_exporter()
    mt5 = _fake_mt5(NAMES12)
    mt5.account_info = lambda: _Acct(login=999, server="Deriv-Real", trade_mode=0)
    with _pt.raises(SystemExit):
        mod.check_demo_account(mt5)

def test_demo_check_refuses_no_login():
    import pytest as _pt
    mod = _load_exporter()
    mt5 = _fake_mt5(NAMES12)
    mt5.account_info = lambda: None
    with _pt.raises(SystemExit):
        mod.check_demo_account(mt5)

def test_export_captures_swap_mode_and_triple_day(tmp_path):
    mod = _load_exporter()
    mt5 = _fake_mt5(["EURUSD"])
    _, spec, _ = mod.export_symbol(mt5, "EURUSD", "EURUSD", tmp_path, 10)
    assert spec["swap_mode"] == 1 and spec["triple_weekday"] == 3
    assert spec["raw_swap_long"] == -0.5 and spec["contract_size"] == 100

def test_export_writes_loader_compatible_csv(tmp_path):
    mod = _load_exporter()
    mt5 = _fake_mt5(["EURUSD"])
    path, spec, n = mod.export_symbol(mt5, "EURUSD", "EURUSD", tmp_path, 10)
    assert n == 10 and spec["mt5_name_raw"] == "EURUSD"
    sys.path.insert(0, ".")
    from trading.csv_loader import load_daily_csv
    bars = load_daily_csv(path, "EURUSD")
    assert len(bars) == 10 and bars[0].symbol == "EURUSD"

def test_exporter_is_read_only():
    src = open("scripts/mt5_export.py").read().lower()
    for banned in ("order_send", "order_check", "positions_get", "buy", "sell"):
        assert banned not in src, f"exporter must stay read-only, found {banned!r}"


def test_mt5_const_falls_back_and_prefers_package():
    mod = _load_exporter()
    mt5 = _fake_mt5(NAMES12)
    assert mod.mt5_const(mt5, "NOPE_CONSTANT", 42) == 42
    mt5.SYMBOL_SWAP_MODE_POINTS = 1
    assert mod.mt5_const(mt5, "SYMBOL_SWAP_MODE_POINTS", 99) == 1

def test_check_mt5_constants_runs_on_any_build(capsys):
    mod = _load_exporter()
    mod.check_mt5_constants(_fake_mt5(NAMES12))  # fake exposes none: notes only
    assert "note" in capsys.readouterr().out

def test_export_stores_mode_name(tmp_path):
    mod = _load_exporter()
    _, spec, _ = mod.export_symbol(_fake_mt5(["EURUSD"]), "EURUSD", "EURUSD", tmp_path, 5)
    assert spec["swap_mode_name"] == "POINTS"
