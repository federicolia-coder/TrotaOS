#!/usr/bin/env python3
"""Trota OS virtual machine tests (QEMU).

Runs the ISO and the installed system in QEMU, without touching any real disk:
every VM uses a fresh qcow2 image under build/vm/.  KVM is used when
available, otherwise TCG emulation (slow but complete).

Scenarios
---------
  boot-iso   Boot the ISO through the firmware and GRUB exactly like a user
             would (BIOS, UEFI or UEFI + Secure Boot); take screenshots.
  live       Boot the live session with a serial console, log in on the
             serial line and run the checks in tests/vm/checks-live.sh.
  install    Fully automatic installation with ubiquity onto a blank virtual
             disk (preseed in tests/vm/install.seed, password generated at
             run time), then the VM powers off.
  installed  Boot the installed disk, log in on the serial console and run
             tests/vm/checks-installed.sh; screenshots of the desktop.

Every run writes serial.log, screenshots and a results file to the output
directory (default build/vm/<scenario>-<firmware>/).

Example:
  sudo tests/vm/vmtest.py install --iso dist/trota-os-1.0-amd64.iso --firmware secureboot
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OVMF = Path("/usr/share/OVMF")


def log(msg: str) -> None:
    print(f"[vmtest {time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --- QMP ---------------------------------------------------------------------
class QMP:
    def __init__(self, path: Path):
        self.sock = socket.socket(socket.AF_UNIX)
        for _ in range(100):
            try:
                self.sock.connect(str(path))
                break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("cannot connect to QMP")
        self.f = self.sock.makefile("rw")
        json.loads(self.f.readline())  # greeting
        self.cmd("qmp_capabilities")

    def cmd(self, name: str, **args):
        self.f.write(json.dumps({"execute": name, "arguments": args}) + "\n")
        self.f.flush()
        while True:
            msg = json.loads(self.f.readline())
            if "return" in msg or "error" in msg:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg["return"]

    def screendump(self, path: Path):
        self.cmd("screendump", filename=str(path), format="png")

    def send_key(self, *keys: str):
        self.cmd("send-key", keys=[{"type": "qcode", "data": k} for k in keys])


# --- serial console ------------------------------------------------------------
class Serial:
    """Reads the VM serial console into a log and allows expect/send."""

    def __init__(self, path: Path, logfile: Path):
        self.sock = socket.socket(socket.AF_UNIX)
        for _ in range(100):
            try:
                self.sock.connect(str(path))
                break
            except OSError:
                time.sleep(0.2)
        self.buf = ""
        self.lock = threading.Lock()
        self.log = open(logfile, "a", encoding="utf-8", errors="replace")
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        while True:
            try:
                data = self.sock.recv(4096)
            except OSError:
                return
            if not data:
                return
            text = data.decode("utf-8", "replace")
            self.log.write(text)
            self.log.flush()
            with self.lock:
                self.buf += text

    def expect(self, pattern: str, timeout: float) -> re.Match:
        rx = re.compile(pattern)
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                m = rx.search(self.buf)
                if m:
                    self.buf = self.buf[m.end():]
                    return m
            time.sleep(0.5)
        raise TimeoutError(f"pattern {pattern!r} not seen within {timeout:.0f}s")

    def send(self, text: str):
        self.sock.sendall(text.encode())

    def run(self, command: str, timeout: float = 300) -> str:
        """Run a shell command and return its output (between markers)."""
        tag = secrets.token_hex(4)
        self.send(f"echo BEGIN-{tag}; {command}; echo END-{tag}-$?\r")
        self.expect(rf"BEGIN-{tag}\r?\n", timeout)
        m = self.expect(rf"([\s\S]*?)END-{tag}-(\d+)", timeout)
        return m.group(1).replace("\r", "")


# --- VM ------------------------------------------------------------------------
class VM:
    def __init__(self, outdir: Path, firmware: str, memory: int = 4096, cpus: int = 4):
        self.out = outdir
        self.firmware = firmware
        self.memory = memory
        self.cpus = cpus
        self.proc = None
        self.qmp = None
        self.serial = None
        self.shots = 0
        outdir.mkdir(parents=True, exist_ok=True)

    def firmware_args(self, vars_file: Path) -> list[str]:
        if self.firmware == "bios":
            return ["-machine", "q35"]
        code = OVMF / ("OVMF_CODE_4M.secboot.fd" if self.firmware == "secureboot" else "OVMF_CODE_4M.fd")
        template = OVMF / ("OVMF_VARS_4M.ms.fd" if self.firmware == "secureboot" else "OVMF_VARS_4M.fd")
        if not vars_file.exists():
            shutil.copy(template, vars_file)
        args = ["-machine", "q35,smm=on" if self.firmware == "secureboot" else "q35",
                "-drive", f"if=pflash,format=raw,unit=0,readonly=on,file={code}",
                "-drive", f"if=pflash,format=raw,unit=1,file={vars_file}"]
        if self.firmware == "secureboot":
            args += ["-global", "driver=cfi.pflash01,property=secure,value=on", "-global", "ICH9-LPC.disable_s3=1"]
        return args

    def start(self, extra: list[str], vars_file: Path, no_reboot: bool = False):
        accel = "kvm" if os.access("/dev/kvm", os.W_OK) else "tcg,thread=multi,tb-size=1024"
        cpu = "host" if accel == "kvm" else "max"
        self.qmp_path = self.out / "qmp.sock"
        self.serial_path = self.out / "serial.sock"
        for p in (self.qmp_path, self.serial_path):
            p.unlink(missing_ok=True)
        cmd = ["qemu-system-x86_64", "-accel", accel, "-cpu", cpu, "-smp", str(self.cpus), "-m", str(self.memory),
               *self.firmware_args(vars_file),
               "-device", "virtio-vga", "-display", "none",
               "-device", "qemu-xhci", "-device", "usb-tablet", "-device", "usb-kbd",
               "-netdev", "user,id=n0", "-device", "virtio-net-pci,netdev=n0",
               "-audiodev", "none,id=snd0", "-device", "intel-hda", "-device", "hda-duplex,audiodev=snd0",
               "-device", "virtio-rng-pci",
               "-chardev", f"socket,id=ser0,path={self.serial_path},server=on,wait=off",
               "-serial", "chardev:ser0",
               "-qmp", f"unix:{self.qmp_path},server=on,wait=off",
               *extra]
        if no_reboot:
            cmd.append("-no-reboot")
        log(f"accel={accel} firmware={self.firmware} mem={self.memory}M")
        (self.out / "qemu-cmdline.txt").write_text(" ".join(cmd) + "\n")
        self.proc = subprocess.Popen(cmd, stdout=open(self.out / "qemu.log", "w"), stderr=subprocess.STDOUT)
        time.sleep(1)
        self.qmp = QMP(self.qmp_path)
        self.serial = Serial(self.serial_path, self.out / "serial.log")

    def screenshot(self, label: str) -> Path | None:
        self.shots += 1
        path = self.out / f"shot-{self.shots:03d}-{label}.png"
        try:
            self.qmp.screendump(path)
            return path
        except Exception as exc:  # VM may be shutting down
            log(f"screenshot failed: {exc}")
            return None

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def wait_exit(self, timeout: float, shot_every: float = 0, label: str = "run") -> bool:
        deadline = time.time() + timeout
        next_shot = time.time() + shot_every if shot_every else None
        while time.time() < deadline:
            if not self.alive():
                return True
            if next_shot and time.time() >= next_shot:
                self.screenshot(label)
                next_shot = time.time() + shot_every
            time.sleep(2)
        return False

    def stop(self):
        if self.alive():
            try:
                self.qmp.cmd("quit")
            except Exception:
                self.proc.kill()
            try:
                self.proc.wait(30)
            except subprocess.TimeoutExpired:
                self.proc.kill()


# --- helpers -------------------------------------------------------------------
def extract_from_iso(iso: Path, dest: Path) -> tuple[Path, Path]:
    dest.mkdir(parents=True, exist_ok=True)
    kernel, initrd = dest / "vmlinuz", dest / "initrd"
    if not kernel.exists() or kernel.stat().st_mtime < iso.stat().st_mtime:
        subprocess.run(["xorriso", "-osirrox", "on", "-indev", str(iso), "-extract", "/casper/vmlinuz", str(kernel),
                        "-extract", "/casper/initrd", str(initrd)], check=True, capture_output=True)
    return kernel, initrd


def newc_cpio(files: dict[str, bytes]) -> bytes:
    """Minimal 'newc' cpio archive (what the kernel expects for initramfs)."""
    out = io.BytesIO()
    ino = 1

    def entry(name: str, data: bytes, mode: int):
        nonlocal ino
        name_b = name.encode() + b"\0"
        hdr = "070701" + "".join(f"{v:08X}" for v in (
            ino, mode, 0, 0, 1, int(time.time()), len(data), 0, 0, 0, 0, len(name_b), 0))
        out.write(hdr.encode() + name_b)
        out.write(b"\0" * ((4 - (110 + len(name_b)) % 4) % 4))
        out.write(data)
        out.write(b"\0" * ((4 - len(data) % 4) % 4))
        ino += 1

    for name, data in files.items():
        entry(name, data, 0o100644)
    entry("TRAILER!!!", b"", 0)
    raw = out.getvalue()
    return raw + b"\0" * ((512 - len(raw) % 512) % 512)


def password_hash(password: str) -> str:
    return subprocess.run(["openssl", "passwd", "-6", "-stdin"], input=password, capture_output=True, text=True,
                          check=True).stdout.strip()


def serial_login(serial: Serial, user: str, password: str, timeout: float):
    serial.send("\r")
    serial.expect(r"login: ", timeout)
    serial.send(user + "\r")
    serial.expect(r"[Pp]assword: ", 60)
    serial.send(password + "\r")
    serial.expect(r"\$ $|\$ \S*$", 180)
    serial.send("export TERM=dumb PAGER=cat SYSTEMD_PAGER=cat; stty -echo cols 200\r")
    time.sleep(2)


def run_checks(serial: Serial, script: Path, out: Path, timeout: float = 1800, subst: dict | None = None) -> dict:
    results = {}
    body = (HERE / "checks-common.sh").read_text() + "\n" + script.read_text()
    for k, v in (subst or {}).items():
        body = body.replace(k, v)
    text = serial.run(f"bash -s <<'TROTA_CHECKS_EOF'\n{body}\nTROTA_CHECKS_EOF", timeout)
    (out / "checks.txt").write_text(text)
    for line in text.splitlines():
        m = re.match(r"^RESULT (\S+) (PASS|FAIL|SKIP)\b(.*)", line)
        if m:
            results[m.group(1)] = {"status": m.group(2), "note": m.group(3).strip()}
    (out / "results.json").write_text(json.dumps(results, indent=2))
    return results


# --- scenarios -------------------------------------------------------------------
def scenario_boot_iso(args, out: Path) -> int:
    vm = VM(out, args.firmware, memory=args.memory)
    vm.start(["-cdrom", str(args.iso), "-boot", "d"], out / "OVMF_VARS.fd")
    try:
        t0 = time.time()
        while time.time() - t0 < args.minutes * 60 and vm.alive():
            vm.screenshot(f"t{int(time.time() - t0):04d}")
            time.sleep(args.interval)
    finally:
        vm.stop()
    log(f"screenshots in {out}")
    return 0


def scenario_live(args, out: Path) -> int:
    kernel, initrd = extract_from_iso(args.iso, out.parent / "iso-boot")
    cmdline = "boot=casper quiet splash console=tty0 console=ttyS0,115200 ---"
    vm = VM(out, args.firmware, memory=args.memory)
    vm.start(["-cdrom", str(args.iso), "-kernel", str(kernel), "-initrd", str(initrd), "-append", cmdline],
             out / "OVMF_VARS.fd")
    try:
        serial_login(vm.serial, "trota", "", timeout=args.minutes * 60)
        log("logged in on the serial console of the live session")
        results = run_checks(vm.serial, HERE / "checks-live.sh", out)
        vm.screenshot("desktop")
    finally:
        vm.stop()
    return report(results, out)


def scenario_install(args, out: Path) -> int:
    kernel, initrd = extract_from_iso(args.iso, out.parent / "iso-boot")
    disk = out.parent / f"disk-{args.firmware}.qcow2"
    disk.unlink(missing_ok=True)
    subprocess.run(["qemu-img", "create", "-f", "qcow2", str(disk), f"{args.disk_gb}G"], check=True,
                   capture_output=True)
    vars_file = out.parent / f"OVMF_VARS-{args.firmware}.fd"
    vars_file.unlink(missing_ok=True)
    password = secrets.token_urlsafe(12)
    (out.parent / f"credentials-{args.firmware}.json").write_text(json.dumps({"user": "tester", "password": password}))
    os.chmod(out.parent / f"credentials-{args.firmware}.json", 0o600)
    seed = (HERE / "install.seed").read_text().replace("@PASSWORD_HASH@", password_hash(password))
    combined = out / "initrd-with-preseed"
    with open(combined, "wb") as f:
        f.write(initrd.read_bytes())
        f.write(gzip.compress(newc_cpio({"preseed.cfg": seed.encode()})))
    cmdline = ("boot=casper automatic-ubiquity noprompt quiet splash "
               "console=tty0 console=ttyS0,115200 ---")
    vm = VM(out, args.firmware, memory=args.memory)
    vm.start(["-cdrom", str(args.iso), "-kernel", str(kernel), "-initrd", str(combined), "-append", cmdline,
              "-drive", f"file={disk},if=virtio,format=qcow2,cache=unsafe"], vars_file, no_reboot=True)
    t0 = time.time()
    finished = vm.wait_exit(args.minutes * 60, shot_every=120, label="install")
    elapsed = time.time() - t0
    if not finished:
        vm.screenshot("timeout")
        vm.stop()
    result = {"install": {"status": "PASS" if finished else "FAIL",
                          "note": f"VM {'powered off/rebooted' if finished else 'still running'} after {elapsed / 60:.1f} min"}}
    (out / "results.json").write_text(json.dumps(result, indent=2))
    return report(result, out)


def scenario_installed(args, out: Path) -> int:
    disk = out.parent / f"disk-{args.firmware}.qcow2"
    creds = json.loads((out.parent / f"credentials-{args.firmware}.json").read_text())
    vars_file = out.parent / f"OVMF_VARS-{args.firmware}.fd"
    vm = VM(out, args.firmware, memory=args.memory)
    vm.start(["-drive", f"file={disk},if=virtio,format=qcow2,cache=unsafe"], vars_file)
    try:
        vm.screenshot("firmware")
        time.sleep(20)
        vm.screenshot("boot")
        serial_login(vm.serial, creds["user"], creds["password"], timeout=args.minutes * 60)
        log("logged in on the serial console of the installed system")
        results = run_checks(vm.serial, HERE / "checks-installed.sh", out, timeout=3600,
                             subst={"@PASSWORD@": creds["password"], "@FIRMWARE@": args.firmware})
        for i in range(3):
            vm.screenshot(f"desktop{i}")
            time.sleep(30)
    finally:
        vm.stop()
    return report(results, out)


def report(results: dict, out: Path) -> int:
    width = max((len(k) for k in results), default=10)
    lines = [f"{k:<{width}}  {v['status']:<4}  {v['note']}" for k, v in results.items()]
    (out / "summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    failed = [k for k, v in results.items() if v["status"] == "FAIL"]
    log(f"{len(results)} checks, {len(failed)} failed — details in {out}")
    return 1 if failed or not results else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenario", choices=["boot-iso", "live", "install", "installed"])
    ap.add_argument("--iso", type=Path, default=ROOT / "dist" / "trota-os-1.0-amd64.iso")
    ap.add_argument("--firmware", choices=["bios", "uefi", "secureboot"], default="uefi")
    ap.add_argument("--memory", type=int, default=4096)
    ap.add_argument("--disk-gb", type=int, default=25)
    ap.add_argument("--minutes", type=float, default=40, help="time limit of the scenario")
    ap.add_argument("--interval", type=float, default=30, help="seconds between screenshots (boot-iso)")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if not shutil.which("qemu-system-x86_64"):
        print("qemu-system-x86_64 is required", file=sys.stderr)
        return 2
    out = args.out or ROOT / "build" / "vm" / f"{args.scenario}-{args.firmware}"
    if out.exists() and args.scenario != "installed":
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    return {"boot-iso": scenario_boot_iso, "live": scenario_live, "install": scenario_install,
            "installed": scenario_installed}[args.scenario](args, out)


if __name__ == "__main__":
    sys.exit(main())
