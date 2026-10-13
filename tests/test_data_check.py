"""Data-check script reports years + spread/swap per symbol (12 symbols)."""
import csv
import subprocess
import sys

SYMS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "XAUUSD", "XAGUSD",
        "US Oil", "UK Brent Oil", "Wall Street 30", "US SP 500", "US Tech 100"]
CANON = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "XAUUSD", "XAGUSD",
         "USOIL", "UKOIL", "US30", "US500", "USTEC"]

def _csv(path, p0):
    import datetime
    base = datetime.date(2019, 1, 1)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["DATE", "TIME", "OPEN", "HIGH", "LOW", "CLOSE", "TICKVOL", "VOL", "SPREAD"])
        p = p0
        for i in range(800):
            day = base + datetime.timedelta(days=i)
            c = p * 1.0001
            w.writerow([day.strftime("%Y.%m.%d"), "00:00", f"{p:.3f}", f"{c*1.001:.3f}",
                        f"{p*0.999:.3f}", f"{c:.3f}", 10, 0, 5])
            p = c

def test_data_check_reports_all_twelve(tmp_path):
    for s, p0 in zip(SYMS, (1.1, 1.3, 110.0, 0.7, 1.3, 1500.0, 18.0, 70.0, 75.0,
                            28000.0, 3200.0, 8500.0)):
        _csv(tmp_path / f"{s}.csv", p0)
    spec = tmp_path / "specs.csv"
    with open(spec, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["canonical", "mt5_name_raw", "contract_size", "spread_price_units",
                    "raw_swap_long", "raw_swap_short", "swap_mode", "swap_point",
                    "swap_tick_value", "swap_tick_size", "triple_weekday",
                    "swap_long_per_unit_night", "swap_short_per_unit_night", "notes"])
        for s in CANON:
            w.writerow([s, s, 1, 0.0002, -5, -2, 1, 0.00001, 1.0, 0.00001, 3,
                        -5e-05, -2e-05, "test"])
    out = subprocess.run([sys.executable, "scripts/data_check.py", "--data", str(tmp_path),
                          "--specs", str(spec)], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    for s in CANON:
        assert s in out.stdout
    assert "Wednesday" in out.stdout  # triple weekday name shown
    assert "2.1" in out.stdout  # ~2.19 years for 800 days

def test_data_check_fails_on_missing(tmp_path):
    out = subprocess.run([sys.executable, "scripts/data_check.py", "--data", str(tmp_path),
                          "--specs", "specs/specs_template.csv"],
                         capture_output=True, text=True)
    assert out.returncode == 1 and "MISSING" in out.stdout
