from trading.mt5_symbols import CANONICAL_SYMBOLS, resolve_symbol

def test_twelve_canonical_symbols():
    assert CANONICAL_SYMBOLS == ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
                                  "XAUUSD", "XAGUSD", "USOIL", "UKOIL",
                                  "US30", "US500", "USTEC"]

def test_aliases_resolve():
    assert resolve_symbol("EURUSD") == "EURUSD"
    assert resolve_symbol("xauusd.s") == "XAUUSD"
    assert resolve_symbol("US Oil") == "USOIL"
    assert resolve_symbol("Wall Street 30") == "US30"
    assert resolve_symbol("US SP 500") == "US500"
    assert resolve_symbol("US Tech 100") == "USTEC"

def test_unknown_returns_none():
    assert resolve_symbol("FOOBAR") is None

def test_new_symbols_resolve():
    assert resolve_symbol("GBPUSD") == "GBPUSD"
    assert resolve_symbol("USDJPY") == "USDJPY"
    assert resolve_symbol("AUDUSD") == "AUDUSD"
    assert resolve_symbol("USDCAD") == "USDCAD"
    assert resolve_symbol("XAGUSD") == "XAGUSD"
    assert resolve_symbol("UK Brent Oil") == "UKOIL"
