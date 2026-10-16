from trota_common import osinfo

TROTA = '''# Trota OS
PRETTY_NAME="Trota OS 1.0"
NAME="Trota OS"
VERSION_ID="24.04"
VERSION="1.0 (Fario)"
VERSION_CODENAME=noble
ID=ubuntu
ID_LIKE=debian
TROTA_VERSION="1.0"
UBUNTU_CODENAME=noble
TROTA_CODENAME="Fario"
TROTA_BASE_VERSION="24.04 LTS"
HOME_URL="https://example.org/"
'''

UBUNTU = '''PRETTY_NAME="Ubuntu 24.04.5 LTS"
NAME="Ubuntu"
VERSION_ID="24.04"
VERSION="24.04.5 LTS (Noble Numbat)"
VERSION_CODENAME=noble
ID=ubuntu
ID_LIKE=debian
UBUNTU_CODENAME=noble
'''


def make_root(tmp_path, os_release, ubuntu=None):
    (tmp_path / "etc").mkdir()
    (tmp_path / "usr/lib").mkdir(parents=True)
    (tmp_path / "etc/os-release").write_text(os_release)
    if ubuntu is not None:
        (tmp_path / "usr/lib/os-release.ubuntu").write_text(ubuntu)
    return str(tmp_path)


def test_parse_quotes_comments_and_escapes():
    d = osinfo.parse_os_release('# c\nA="x y"\nB=\'q\'\nC=plain\nD="a \\"b\\""\nbad line\n=x\n')
    assert d == {"A": "x y", "B": "q", "C": "plain", "D": 'a "b"'}


def test_parse_unbalanced_quotes_does_not_raise():
    assert osinfo.parse_os_release('A="broken\n')["A"] == "broken"


def test_trota_release_with_diverted_ubuntu_file(tmp_path):
    rel = osinfo.release_info(make_root(tmp_path, TROTA, UBUNTU))
    assert rel.is_trota
    assert rel.name == "Trota OS" and rel.version == "1.0" and rel.codename == "Fario"
    assert rel.base_description == "Ubuntu 24.04.5 LTS (Noble Numbat)"
    assert rel.base_codename == "noble"


def test_trota_release_without_diverted_file_uses_vendor_field(tmp_path):
    rel = osinfo.release_info(make_root(tmp_path, TROTA))
    assert rel.base_description == "Ubuntu 24.04 LTS"


def test_plain_ubuntu(tmp_path):
    rel = osinfo.release_info(make_root(tmp_path, UBUNTU))
    assert not rel.is_trota
    assert rel.pretty_name == "Ubuntu 24.04.5 LTS"
    assert rel.base_name == "Ubuntu"


def test_missing_files(tmp_path):
    rel = osinfo.release_info(str(tmp_path))
    assert rel.name == "Linux" and not rel.is_trota
