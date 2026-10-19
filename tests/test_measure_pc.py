"""scripts/verify/measure-pc.py: parsing of systemd-analyze and free, median of runs."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("measure_pc", Path(__file__).resolve().parent.parent / "scripts/verify/measure-pc.py")
mp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mp)


def test_boot_times_uefi():
    out = mp.boot_times("Startup finished in 7.402s (firmware) + 3.101s (loader) + 873ms (kernel) + 1min 2.5s (userspace) = 1min 13.876s\n"
                        "graphical.target reached after 5.879s in userspace.\n")
    assert out == {"firmware_s": 7.4, "loader_s": 3.1, "kernel_s": 0.87, "userspace_s": 62.5, "graphical_s": 5.88, "system_boot_s": 6.75}


def test_boot_times_bios_without_graphical():
    out = mp.boot_times("Startup finished in 2.233s (kernel) + 11.2s (userspace) = 13.4s\nmulti-user.target reached after 11s in userspace.\n")
    assert out == {"kernel_s": 2.23, "userspace_s": 11.2}


def test_memory():
    free = "               total        used        free      shared  buff/cache   available\nMem:            7843         912        5200         120        1730        6931\nSwap:           2047           0        2047\n"
    assert mp.memory(free) == {"ram_total_mb": 7843, "ram_used_mb": 912, "ram_available_mb": 6931}


def test_problems_flags_bad_conditions():
    d = {"session_age_s": 20, "apps_open": ["firefox"], "ac_power": False}
    issues = mp.problems(d, "ubuntu")
    assert len(issues) >= 4


def test_median_of_three_runs():
    runs = [{"model": "X", "system_boot_s": s, "ram_used_mb": r} for s, r in ((9.0, 900), (7.0, 950), (8.0, 1000))]
    m = mp.median_of(runs)
    assert m["system_boot_s"] == 8.0 and m["ram_used_mb"] == 950 and m["runs"] == 3
