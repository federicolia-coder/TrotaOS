"""trota-vr: checks of a PC for virtual reality, with recorded command output."""

import json

import pytest

from conftest import FakeRunner, fail, ok
from trota_vr import checks as vr

LSPCI_NVIDIA = """\
00:02.0 VGA compatible controller [0300]: Intel Corporation UHD Graphics 630 [8086:3e92]
\tSubsystem: Dell Device [1028:085a]
\tKernel driver in use: i915
\tKernel modules: i915
01:00.0 VGA compatible controller [0300]: NVIDIA Corporation TU106 [GeForce RTX 2060] [10de:1f08] (rev a1)
\tSubsystem: Dell Device [1028:085a]
\tKernel driver in use: {driver}
\tKernel modules: nvidiafb, nouveau, nvidia_drm, nvidia
00:1f.3 Audio device [0403]: Intel Corporation Cannon Lake PCH cAVS [8086:a348] (rev 10)
\tKernel driver in use: snd_hda_intel
"""

LSPCI_AMD = """\
03:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Navi 23 [Radeon RX 6600] [1002:73ff] (rev c7)
\tKernel driver in use: amdgpu
"""

LSPCI_INTEL = """\
00:02.0 VGA compatible controller [0300]: Intel Corporation Alder Lake-P GT2 [Iris Xe Graphics] [8086:46a6] (rev 0c)
\tKernel driver in use: i915
"""

VULKAN = """\
Devices:
========
GPU0:
\tapiVersion         = 1.3.274
\tdeviceType         = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
\tdeviceName         = AMD Radeon RX 6600 (RADV NAVI23)
GPU1:
\tdeviceType         = PHYSICAL_DEVICE_TYPE_CPU
\tdeviceName         = llvmpipe (LLVM 17.0.6, 256 bits)
"""


def ctx(tmp_path, responses=None):
    return vr.Context(runner=FakeRunner(responses or {}), root=tmp_path, home=tmp_path / "home")


def test_parse_lspci_keeps_only_gpus_with_driver():
    gpus = vr.parse_lspci(LSPCI_NVIDIA.format(driver="nvidia"))
    assert [(g.vendor, g.driver) for g in gpus] == [("8086", "i915"), ("10de", "nvidia")]
    assert "GeForce RTX 2060" in gpus[1].name


@pytest.mark.parametrize("text,status", [
    (LSPCI_NVIDIA.format(driver="nvidia"), vr.OK),
    (LSPCI_NVIDIA.format(driver="nouveau"), vr.WARNING),
    (LSPCI_AMD, vr.OK),
    (LSPCI_INTEL, vr.WARNING),
    ("", vr.WARNING),
])
def test_gpu_status(tmp_path, text, status):
    r = vr.check_gpu(ctx(tmp_path, {("lspci",): ok(text)}))
    assert r.status == status


def test_gpu_nouveau_suggests_driver(tmp_path):
    r = vr.check_gpu(ctx(tmp_path, {("lspci",): ok(LSPCI_NVIDIA.format(driver="nouveau"))}))
    assert "NVIDIA" in r.suggestion


def test_vulkan_ignores_software_renderer(tmp_path):
    assert vr.parse_vulkaninfo(VULKAN)[1] == ("llvmpipe (LLVM 17.0.6, 256 bits)", "CPU")
    r = vr.check_vulkan(ctx(tmp_path, {("vulkaninfo",): ok(VULKAN)}))
    assert r.status == vr.OK and "RX 6600" in r.summary
    only_cpu = VULKAN.split("GPU1:")[0].replace("DISCRETE_GPU", "CPU")
    assert vr.check_vulkan(ctx(tmp_path, {("vulkaninfo",): ok(only_cpu)})).status == vr.ERROR
    assert vr.check_vulkan(ctx(tmp_path)).status == vr.ERROR    # vulkaninfo missing


def test_headset_detection(tmp_path):
    lsusb = ("Bus 001 Device 002: ID 8087:0029 Intel Corp. AX200 Bluetooth\n"
             "Bus 003 Device 007: ID 28de:2102 Valve Software VR Radio & HMD Mic\n")
    r = vr.check_headset(ctx(tmp_path, {("lsusb",): ok(lsusb)}))
    assert r.status == vr.OK and r.details == ["Valve Software VR Radio & HMD Mic"]
    assert vr.check_headset(ctx(tmp_path, {("lsusb",): ok("")})).status == vr.INFO


def test_runtime_from_system_file(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert vr.check_runtime(ctx(tmp_path)).status == vr.WARNING
    f = tmp_path / "etc/xdg/openxr/1/active_runtime.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"runtime": {"name": "Monado", "library_path": "../../../lib/libopenxr_monado.so"}}))
    r = vr.check_runtime(ctx(tmp_path))
    assert r.status == vr.OK and "Monado" in r.summary


def test_user_runtime_wins(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    user = tmp_path / "home/.config/openxr/1/active_runtime.json"
    user.parent.mkdir(parents=True)
    user.write_text(json.dumps({"runtime": {"library_path": "/app/lib/wivrn/libopenxr_wivrn.so"}}))
    assert "WiVRn" in vr.check_runtime(ctx(tmp_path)).summary


def test_udev_rules(tmp_path):
    d = tmp_path / "usr/lib/udev/rules.d"
    d.mkdir(parents=True)
    (d / "70-xrhardware.rules").write_text("")
    assert vr.check_udev(ctx(tmp_path)).status == vr.WARNING
    (d / "60-steam-vr.rules").write_text("")
    assert vr.check_udev(ctx(tmp_path)).status == vr.OK


def test_software_and_install_command(tmp_path):
    r = vr.check_software(ctx(tmp_path, {("flatpak", "list"): ok("org.mozilla.Thunderbird\nio.github.wivrn.wivrn\n")}))
    assert r.status == vr.OK
    assert vr.check_software(ctx(tmp_path, {("flatpak", "list"): ok("")})).status == vr.INFO
    cmd = vr.install_command(vr.find_app("steam"))
    assert cmd[:2] == ("flatpak", "install") and cmd[-2:] == ("flathub", "com.valvesoftware.Steam")
    runner = FakeRunner({("flatpak", "install"): fail(1, stderr="error: denied")})
    assert not vr.install(vr.find_app("wivrn"), vr.Context(runner=runner)).ok


def test_one_broken_check_does_not_stop_the_others(tmp_path, monkeypatch):
    def boom(_ctx):
        raise RuntimeError("boom")
    monkeypatch.setattr(vr, "CHECKS", (boom, vr.check_headset))
    results = vr.run_all(ctx(tmp_path, {("lsusb",): ok("")}))
    assert [r.status for r in results] == ["skipped", vr.INFO]
