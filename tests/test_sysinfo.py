import json
from collections import namedtuple

from conftest import FakeRunner, fail, ok
from trota_common import sysinfo

CPUINFO = """processor\t: 0
model name\t: AMD Ryzen 7 5800X  8-Core Processor
physical id\t: 0
core id\t\t: 0

processor\t: 1
model name\t: AMD Ryzen 7 5800X  8-Core Processor
physical id\t: 0
core id\t\t: 0

processor\t: 2
model name\t: AMD Ryzen 7 5800X  8-Core Processor
physical id\t: 0
core id\t\t: 1
"""

MEMINFO = """MemTotal:       16303580 kB
MemFree:         1000000 kB
MemAvailable:    8151790 kB
SwapTotal:       2097148 kB
SwapFree:        2097148 kB
"""

Usage = namedtuple("Usage", "total used free")


def test_format_bytes():
    assert sysinfo.format_bytes(0) == "0 B"
    assert sysinfo.format_bytes(1536) == "1.5 KiB"
    assert sysinfo.format_bytes(16 * 1024**3) == "16.0 GiB"
    assert sysinfo.format_bytes(None) == "—"


def test_format_duration():
    assert sysinfo.format_duration(59) == "0 min"
    assert sysinfo.format_duration(3 * 3600 + 120) == "3 h 2 min"
    assert sysinfo.format_duration(2 * 86400 + 60) == "2 d 0 h 1 min"
    assert sysinfo.format_duration(None) == "—"


def test_cpu_info(tmp_path):
    (tmp_path / "cpuinfo").write_text(CPUINFO)
    sysdir = tmp_path / "sys/devices/system/cpu/cpu0/cpufreq"
    sysdir.mkdir(parents=True)
    (sysdir / "cpuinfo_max_freq").write_text("4850000\n")
    info = sysinfo.cpu_info(tmp_path, tmp_path / "sys")
    assert info.model == "AMD Ryzen 7 5800X 8-Core Processor"
    assert info.logical_cpus == 3
    assert info.physical_cores == 2
    assert info.max_mhz == 4850.0


def test_cpu_info_unreadable(tmp_path):
    info = sysinfo.cpu_info(tmp_path, tmp_path)
    assert info.model == "Unknown" and info.physical_cores is None


def test_memory_info(tmp_path):
    (tmp_path / "meminfo").write_text(MEMINFO)
    m = sysinfo.memory_info(tmp_path)
    assert m.total_bytes == 16303580 * 1024
    assert m.available_bytes == 8151790 * 1024
    assert m.swap_total_bytes == 2097148 * 1024


def test_disk_info_filters_pseudo_filesystems(tmp_path):
    mounts = tmp_path / "mounts"
    mounts.write_text(
        "/dev/nvme0n1p2 / ext4 rw 0 0\n"
        "proc /proc proc rw 0 0\n"
        "tmpfs /run tmpfs rw 0 0\n"
        "/dev/loop3 /snap/firefox/1 squashfs ro 0 0\n"
        "/dev/nvme0n1p1 /boot/efi vfat rw 0 0\n"
        "/dev/sda1 /media/user/My\\040Disk exfat rw 0 0\n"
        "/dev/nvme0n1p2 /var/lib/docker ext4 rw 0 0\n"
    )
    sizes = {"/": Usage(100, 40, 60), "/boot/efi": Usage(10, 1, 9), "/media/user/My Disk": Usage(50, 25, 25)}
    disks = sysinfo.disk_info(mounts, usage=lambda p: sizes[p])
    assert [d.mountpoint for d in disks] == ["/", "/boot/efi", "/media/user/My Disk"]
    assert disks[0].used_percent == 40.0


def test_disk_info_overlay_root_live_session(tmp_path):
    mounts = tmp_path / "mounts"
    mounts.write_text("/cow / overlay rw 0 0\n")
    disks = sysinfo.disk_info(mounts, usage=lambda p: Usage(10, 5, 5))
    assert len(disks) == 1 and disks[0].fstype == "overlay"


def test_disk_info_unreadable_mount_is_skipped(tmp_path):
    mounts = tmp_path / "mounts"
    mounts.write_text("/dev/sda1 / ext4 rw 0 0\n/dev/sdb1 /data ext4 rw 0 0\n")

    def usage(p):
        if p == "/data":
            raise PermissionError(13, "denied")
        return Usage(10, 5, 5)

    assert [d.mountpoint for d in sysinfo.disk_info(mounts, usage=usage)] == ["/"]


def test_network_info(tmp_path):
    for name, files in {
        "lo": {"operstate": "unknown", "address": "00:00:00:00:00:00", "type": "772"},
        "enp3s0": {"operstate": "up", "address": "aa:bb:cc:dd:ee:ff", "type": "1", "device": None},
        "wlp2s0": {"operstate": "down", "address": "11:22:33:44:55:66", "type": "1", "device": None, "wireless": None},
        "docker0": {"operstate": "down", "address": "02:42:00:00:00:01", "type": "1"},
    }.items():
        d = tmp_path / name
        d.mkdir()
        for f, content in files.items():
            if content is None:
                (d / f).mkdir()
            else:
                (d / f).write_text(content + "\n")
    ip_json = json.dumps([{"ifname": "enp3s0", "addr_info": [{"local": "192.168.1.10", "prefixlen": 24},
                                                             {"local": "fe80::1", "prefixlen": 64}]}])
    runner = FakeRunner({("ip", "-j", "addr", "show"): ok(ip_json)})
    nets = {n.name: n for n in sysinfo.network_info(tmp_path, runner)}
    assert nets["lo"].kind == "loopback"
    assert nets["enp3s0"].kind == "ethernet" and nets["enp3s0"].state == "up"
    assert nets["enp3s0"].addresses == ["192.168.1.10/24", "fe80::1/64"]
    assert nets["wlp2s0"].kind == "wireless"
    assert nets["docker0"].kind == "virtual"


def test_network_info_without_ip_command(tmp_path):
    (tmp_path / "eth0").mkdir()
    nets = sysinfo.network_info(tmp_path, FakeRunner())
    assert nets[0].name == "eth0" and nets[0].addresses == []


def test_network_info_bad_json(tmp_path):
    runner = FakeRunner({("ip",): ok("not json")})
    assert sysinfo.network_info(tmp_path, runner) == []


def test_gpu_info():
    out = ('00:02.0 "VGA compatible controller" "Intel Corporation" "Alder Lake-P GT2" -r0c "Lenovo" "x"\n'
           '01:00.0 "3D controller" "NVIDIA Corporation" "GA107M" -ra1 "Lenovo" "y"\n'
           '00:1f.3 "Audio device" "Intel Corporation" "HDA" "z" "w"\n')
    gpus = sysinfo.gpu_info(FakeRunner({("lspci", "-mm"): ok(out)}))
    assert gpus == ["Intel Corporation Alder Lake-P GT2", "NVIDIA Corporation GA107M"]


def test_gpu_info_without_lspci():
    assert sysinfo.gpu_info(FakeRunner()) == []
    assert sysinfo.gpu_info(FakeRunner({("lspci",): fail()})) == []


def test_desktop_info():
    env = {"XDG_CURRENT_DESKTOP": "ubuntu:GNOME", "XDG_SESSION_TYPE": "wayland"}
    runner = FakeRunner({("gnome-shell", "--version"): ok("GNOME Shell 46.0\n")})
    assert sysinfo.desktop_info(env, runner) == ("GNOME Shell 46.0", "wayland")
    assert sysinfo.desktop_info({}, FakeRunner()) == ("—", "—")


def test_collect_and_serialise_real_system():
    report = sysinfo.collect()
    data = json.loads(report.to_json())
    assert data["kernel"] and data["architecture"]
    assert data["memory"]["total_bytes"] > 0
    text = sysinfo.report_text(report)
    assert "Kernel" in text and "Memory" in text


def test_collect_makes_no_network_connections(monkeypatch):
    import socket

    def forbidden(*a, **k):
        raise AssertionError("sysinfo must not open network connections")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    sysinfo.collect()
