import csv
from pathlib import Path
import pytest
from trading.csv_loader import load_daily_csv, load_data_dir

def _write(path, rows, header=("DATE","TIME","OPEN","HIGH","LOW","CLOSE","TICKVOL","VOL","SPREAD")):
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)

def test_mt5_format(tmp_path):
    p = tmp_path / "EURUSD.csv"
    _write(p, [["2020.01.01","00:00","1.100","1.105","1.098","1.102",100,0,10],
               ["2020.01.02","00:00","1.102","1.108","1.100","1.106",100,0,10]])
    bars = load_daily_csv(p, "EURUSD")
    assert [b.close for b in bars] == [1.102, 1.106]
    assert bars[0].epoch < bars[1].epoch and bars[0].symbol == "EURUSD"

def test_generic_format(tmp_path):
    p = tmp_path / "x.csv"
    _write(p, [["2020-01-01","1.0","1.1","0.9","1.05"]], header=("date","open","high","low","close"))
    bars = load_daily_csv(p, "XAUUSD")
    assert len(bars) == 1 and bars[0].symbol == "XAUUSD"

def test_bad_ohlc_rejected(tmp_path):
    p = tmp_path / "bad.csv"
    _write(p, [["2020.01.01","00:00","1.1","1.0","1.2","1.15",1,0,0]])  # H<L O/C
    with pytest.raises(ValueError):
        load_daily_csv(p, "EURUSD")

def test_data_dir_aliases_and_missing(tmp_path):
    _write(tmp_path / "US Oil.csv", [["2020.01.01","00:00","70","71","69","70.5",1,0,0]])
    by_sym, missing = load_data_dir(tmp_path)
    assert "USOIL" in by_sym and "EURUSD" in missing and len(missing) == 11
