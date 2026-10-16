import pytest

from conftest import FakeRunner, fail, ok
from trota_common import packages as pk

SHOW = """Package: htop
Architecture: amd64
Version: 3.3.0-4build1
Priority: optional
Section: utils
Origin: Ubuntu
Maintainer: Ubuntu Developers <ubuntu-devel-discuss@lists.ubuntu.com>
Installed-Size: 424
Depends: libc6 (>= 2.38), libncursesw6 (>= 6), libnl-3-200 (>= 3.2.7)
Filename: pool/main/h/htop/htop_3.3.0-4build1_amd64.deb
Size: 171972
Homepage: https://htop.dev/
Description-en: interactive processes viewer
 Htop is an ncursed-based process viewer similar to top, but it
 allows one to scroll the list vertically and horizontally.
 .
 Tasks related to processes (killing, renicing) can be done
 without entering their PIDs.
Description-md5: 8eb5aa19b3c92a975dc78e2165f6688d

Package: htop
Version: 3.3.0-4
"""


@pytest.mark.parametrize("name,valid", [
    ("htop", True), ("g++", True), ("libc6", True), ("python3.12-venv", True),
    ("Htop", False), ("-rf", False), ("a", False), ("htop; rm -rf /", False), ("", False), ("ht op", False),
])
def test_package_name_validation(name, valid):
    assert pk.is_valid_package_name(name) is valid


def test_search_escapes_regex_and_ranks():
    out = "python3-foo - something\npython3 - interactive language\nlibpython3 - library\nbad line\n"
    runner = FakeRunner({("apt-cache", "search"): ok(out)})
    res = pk.search("python3", runner)
    assert [r.name for r in res] == ["python3", "python3-foo", "libpython3"]
    res = pk.search("c++ (x", runner)
    assert runner.calls[-1] == ("apt-cache", "search", r"c\+\+", r"\(x")


def test_search_limits_results():
    out = "".join(f"pkg{i:03d} - x\n" for i in range(500))
    assert len(pk.search("pkg", FakeRunner({("apt-cache",): ok(out)}), limit=50)) == 50


@pytest.mark.parametrize("query", ["", "   ", "x" * 65, "a\nb"])
def test_search_rejects_bad_queries(query):
    with pytest.raises(pk.PackageError):
        pk.search(query, FakeRunner())


def test_search_errors():
    with pytest.raises(pk.PackageError):
        pk.search("htop", FakeRunner())   # apt-cache missing
    with pytest.raises(pk.PackageError):
        pk.search("htop", FakeRunner({("apt-cache",): fail(100, stderr="E: broken")}))


def test_info_parses_first_stanza_and_installed_state():
    runner = FakeRunner({
        ("apt-cache", "show"): ok(SHOW),
        ("dpkg-query",): ok("ii \t3.3.0-4build1"),
    })
    info = pk.info("htop", runner)
    assert info.version == "3.3.0-4build1"
    assert info.summary == "interactive processes viewer"
    assert info.description.startswith("Htop is an ncursed-based process viewer similar to top, but it allows")
    assert "\n\nTasks related" in info.description
    assert info.installed and info.installed_version == "3.3.0-4build1"
    assert info.installed_size_kib == 424 and info.download_size == 171972
    assert info.component == "main" and info.homepage == "https://htop.dev/"
    assert info.depends[0] == "libc6 (>= 2.38)"


def test_info_not_installed_and_component():
    show = SHOW.replace("Section: utils", "Section: universe/games")
    runner = FakeRunner({("apt-cache", "show"): ok(show), ("dpkg-query",): fail(1)})
    info = pk.info("htop", runner)
    assert not info.installed and info.component == "universe"
    assert "community" in info.support_note


def test_info_rc_state_is_not_installed():
    runner = FakeRunner({("apt-cache", "show"): ok(SHOW), ("dpkg-query",): ok("rc \t3.3.0")})
    assert not pk.info("htop", runner).installed


def test_info_invalid_or_unknown():
    with pytest.raises(pk.PackageError):
        pk.info("../../etc/passwd", FakeRunner())
    with pytest.raises(pk.PackageError):
        pk.info("nonexistent", FakeRunner({("apt-cache", "show"): fail(100)}))


def test_commands():
    assert pk.install_command("htop") == "sudo apt install htop"
    assert pk.remove_command("htop") == "sudo apt remove htop"
    with pytest.raises(pk.PackageError):
        pk.install_command("htop && curl evil")


def test_lists_available():
    assert pk.lists_available(FakeRunner({("apt-cache", "stats"): ok("Total package names: 106123 (2,972 k)\n")}))
    assert not pk.lists_available(FakeRunner({("apt-cache", "stats"): ok("Total package names: 120 (1 k)\n")}))
    assert not pk.lists_available(FakeRunner())


def test_never_runs_privileged_commands():
    runner = FakeRunner({("apt-cache",): ok(SHOW), ("dpkg-query",): ok("ii \t1")})
    pk.search("htop", runner)
    pk.info("htop", runner)
    pk.lists_available(runner)
    assert all(c[0] in ("apt-cache", "dpkg-query") for c in runner.calls)
