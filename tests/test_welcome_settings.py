from trota_welcome import settings


def test_default_is_show(tmp_path):
    assert settings.show_at_login(tmp_path / "missing.ini") is True


def test_roundtrip(tmp_path):
    p = tmp_path / "trota-os" / "welcome.ini"
    settings.set_show_at_login(False, p)
    assert settings.show_at_login(p) is False
    settings.set_show_at_login(True, p)
    assert settings.show_at_login(p) is True
    assert not list(p.parent.glob("*.tmp"))


def test_corrupt_file_falls_back_to_default(tmp_path):
    p = tmp_path / "welcome.ini"
    p.write_text("this is [not an ini\n")
    assert settings.show_at_login(p) is True
    settings.set_show_at_login(False, p)   # overwrites the corrupt file
    assert settings.show_at_login(p) is False


def test_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert settings.config_path() == tmp_path / "trota-os" / "welcome.ini"


def test_autostart_exits_when_disabled(monkeypatch, tmp_path):
    """`trota-welcome --autostart` must not open a window when disabled."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    settings.set_show_at_login(False)
    import sys

    from trota_welcome import cli

    sys.modules.pop("gi.repository.Gtk", None)
    assert cli.main(["trota-welcome", "--autostart"]) == 0
    assert "gi.repository.Gtk" not in sys.modules, "GTK must not be loaded"
