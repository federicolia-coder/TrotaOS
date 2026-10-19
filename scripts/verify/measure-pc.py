#!/usr/bin/env python3
"""Measure Trota OS on a real PC, the same way the virtual-machine tests do.

Run it on an installed Trota OS (not the live session), as the normal user,
in the graphical session, at least 60 seconds after logging in and with no
application open. Every run is appended to ~/trota-misure.jsonl; after three
cold boots the script prints the median of the three, ready for
website/benchmarks.json.

    python3 measure-pc.py            # one measurement
    python3 measure-pc.py --wait     # first wait until the session is 60 s old

Read-only: it reads /proc, /sys and the output of systemd-analyze, lsblk,
lspci and free. It sends nothing anywhere.
"""
import argparse
import datetime
import json
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

LOG = Path.home() / "trota-misure.jsonl"
MIN_SESSION_S = 60
# Applications that, if open, make the memory figure not comparable.
APPS = ("firefox", "soffice.bin", "thunderbird", "code", "gimp", "libreoffice")


def run(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30, env={**os.environ, "LC_ALL": "C"}).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ""


def seconds(text):
    """'1min 2.345s' or '873ms' -> seconds."""
    total = 0.0
    for value, unit in re.findall(r"([\d.]+)\s*(min|ms|s)\b", text):
        total += float(value) * {"min": 60, "s": 1, "ms": 0.001}[unit]
    return round(total, 2)


def boot_times(analyze):
    """Parse `systemd-analyze` (default verb `time`)."""
    out = {}
    first = analyze.split(" = ")[0]
    for part in first.split("+"):
        m = re.search(r"([\d.]+\s*(?:min\s*[\d.]+\s*)?(?:ms|s|min))\s*\((\w+)\)", part)
        if m:
            out[m.group(2) + "_s"] = seconds(m.group(1))
    g = re.search(r"graphical\.target reached after (.+?) in userspace", analyze)
    if g:
        out["graphical_s"] = seconds(g.group(1))
    # The part Trota OS controls: kernel + userspace until the login screen.
    if "kernel_s" in out and "graphical_s" in out:
        out["system_boot_s"] = round(out["kernel_s"] + out["graphical_s"], 2)
    return out


def memory(free):
    for line in free.splitlines():
        if line.startswith("Mem:"):
            f = line.split()
            return {"ram_total_mb": int(f[1]), "ram_used_mb": int(f[2]), "ram_available_mb": int(f[6])}
    return {}


def disk():
    src = run("findmnt", "-no", "SOURCE", "/").strip()
    name = ""
    for line in run("lsblk", "-rsno", "NAME,TYPE", src).splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == "disk":
            name = parts[0]
    if not name:
        return "sconosciuto"
    rota, tran, model = (run("lsblk", "-dno", "ROTA,TRAN,MODEL", "/dev/" + name).split(None, 2) + ["", "", ""])[:3]
    kind = "HDD" if rota == "1" else ("SSD NVMe" if tran == "nvme" else "SSD SATA" if tran == "sata" else "SSD")
    return (kind + " " + model.strip()).strip()


def session_age():
    pid = run("pgrep", "-u", str(os.getuid()), "-o", "gnome-shell").strip()
    age = run("ps", "-o", "etimes=", "-p", pid).strip() if pid else ""
    return int(age) if age.isdigit() else None


def collect():
    osr = dict(re.findall(r'^(\w+)="?([^"\n]*)"?$', read("/etc/os-release"), re.M))
    cpu = re.search(r"Model name:\s*(.+)", run("lscpu"))
    gpu = [l.split(": ", 1)[-1] for l in run("lspci").splitlines() if re.search(r"VGA|3D|Display", l)]
    ac = [read(p / "online") for p in Path("/sys/class/power_supply").glob("*") if read(p / "type") == "Mains"]
    procs = run("ps", "-u", str(os.getuid()), "-o", "comm=").split()
    data = {
        "date": datetime.date.today().isoformat(),
        "system": osr.get("PRETTY_NAME", ""),
        "edition": osr.get("VARIANT", "Desktop"),
        "model": " ".join(x for x in (read("/sys/class/dmi/id/sys_vendor"), read("/sys/class/dmi/id/product_name"),
                                      read("/sys/class/dmi/id/product_version")) if x and x.lower() not in ("none", "default string")),
        "cpu": cpu.group(1).strip() if cpu else "",
        "threads": os.cpu_count(),
        "disk": disk(),
        "gpu": "; ".join(gpu),
        "kernel": os.uname().release,
        "ac_power": ("1" in ac) if ac else None,
        "session_age_s": session_age(),
        "apps_open": sorted({p for p in procs if p in APPS}),
    }
    data.update(boot_times(run("systemd-analyze")))
    data.update(memory(run("free", "-m")))
    return data


def problems(d, osr_id):
    out = []
    if osr_id != "trota":
        out.append("questo sistema non è Trota OS")
    if Path("/cdrom/casper").exists() or "boot=casper" in read("/proc/cmdline"):
        out.append("è la sessione live: misura il sistema installato")
    if d["session_age_s"] is None:
        out.append("nessuna sessione grafica trovata: esegui il comando dal desktop")
    elif d["session_age_s"] < MIN_SESSION_S:
        out.append(f"accesso fatto da {d['session_age_s']} s: aspetta almeno {MIN_SESSION_S} s (o usa --wait)")
    if d["apps_open"]:
        out.append("applicazioni aperte: " + ", ".join(d["apps_open"]) + " (chiudile e riavvia)")
    if d["ac_power"] is False:
        out.append("il PC va a batteria: collega l'alimentatore")
    return out


def median_of(runs):
    keys = ("system_boot_s", "firmware_s", "loader_s", "ram_used_mb")
    out = dict(runs[-1])
    for k in keys:
        vals = [r[k] for r in runs if isinstance(r.get(k), (int, float))]
        if vals:
            out[k] = statistics.median(vals)
    out["runs"] = len(runs)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--wait", action="store_true", help="aspetta che la sessione abbia almeno 60 s")
    args = ap.parse_args()
    if args.wait:
        age = session_age()
        if age is not None and age < MIN_SESSION_S:
            print(f"Attendo {MIN_SESSION_S - age} s…")
            time.sleep(MIN_SESSION_S - age)
    d = collect()
    osr_id = dict(re.findall(r'^(\w+)="?([^"\n]*)"?$', read("/etc/os-release"), re.M)).get("ID", "")
    issues = problems(d, osr_id)
    print(f"Computer   {d['model'] or 'sconosciuto'}")
    print(f"Processore {d['cpu']} ({d['threads']} thread)")
    print(f"Memoria    {d.get('ram_total_mb', '?')} MB · disco {d['disk']}")
    print(f"Avvio      {d.get('system_boot_s', '?')} s (kernel + sistema fino alla schermata di accesso);"
          f" firmware {d.get('firmware_s', '?')} s, bootloader {d.get('loader_s', '?')} s")
    print(f"RAM usata  {d.get('ram_used_mb', '?')} MB dopo l'accesso ({d['session_age_s']} s di sessione)")
    if issues:
        print("\nMisura NON valida per il sito:\n  - " + "\n  - ".join(issues))
        return 1
    with LOG.open("a") as f:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")
    runs = [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()]
    runs = [r for r in runs if r.get("model") == d["model"] and r.get("system") == d["system"]][-3:]
    print(f"\nSalvata in {LOG} (misura {len(runs)} di 3 per questo computer).")
    if len(runs) < 3:
        print("Spegni il PC, riaccendilo, accedi e rilancia il comando.")
    else:
        print("\nMediana delle ultime 3 misure, da aggiungere a website/benchmarks.json:\n")
        print(json.dumps(median_of(runs), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
