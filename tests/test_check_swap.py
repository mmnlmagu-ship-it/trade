"""check_swap.py: engine prediction vs terminal reading."""
import csv
import subprocess
import sys

HEADER = ["canonical", "mt5_name_raw", "contract_size", "spread_price_units",
          "raw_swap_long", "raw_swap_short", "swap_mode", "swap_mode_name",
          "swap_point", "swap_tick_value", "swap_tick_size", "triple_weekday",
          "swap_long_per_unit_night", "swap_short_per_unit_night", "notes"]

def _specs(tmp_path):
    p = tmp_path / "specs.csv"
    with open(p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerow(["EURUSD", "EURUSD", 100000, 0.00002, -5, -2, 1, "POINTS",
                    0.00001, 1, 0.00001, 3, "", "", "t"])
    return p

def _run(spec, *args):
    return subprocess.run([sys.executable, "scripts/check_swap.py", "--specs", str(spec),
                           *args], capture_output=True, text=True)

def test_agree_within_tolerance(tmp_path):
    spec = _specs(tmp_path)
    out = _run(spec, "--symbol", "EURUSD", "--side", "buy", "--lots", "0.001",
               "--nights", "7", "--from", "2021-01-04",
               "--observed", str(100 * -5e-05 * 7))
    assert out.returncode == 0, out.stdout
    assert "AGREE" in out.stdout

def test_mismatch_flagged(tmp_path):
    spec = _specs(tmp_path)
    out = _run(spec, "--symbol", "EURUSD", "--side", "buy", "--lots", "1",
               "--nights", "1", "--from", "2021-01-04", "--observed", "-999.0")
    assert out.returncode == 1 and "MISMATCH" in out.stdout

def test_unknown_symbol_exits(tmp_path):
    spec = _specs(tmp_path)
    out = _run(spec, "--symbol", "NOPE", "--side", "buy", "--lots", "1",
               "--nights", "1", "--from", "2021-01-04", "--observed", "0")
    assert out.returncode != 0
