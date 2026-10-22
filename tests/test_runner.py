from trota_common import runner


def test_run_success():
    r = runner.run(["echo", "hello"])
    assert r.ok and r.stdout.strip() == "hello"


def test_run_missing_command():
    r = runner.run(["definitely-not-a-real-command-trota"])
    assert r.missing and not r.ok and r.returncode is None


def test_run_nonzero_exit():
    r = runner.run(["sh", "-c", "echo err >&2; exit 3"])
    assert r.returncode == 3 and not r.ok and "err" in r.stderr


def test_run_timeout():
    r = runner.run(["sleep", "5"], timeout=0.2)
    assert r.timed_out and not r.ok


def test_run_uses_c_locale():
    r = runner.run(["sh", "-c", "echo $LC_ALL"])
    assert r.stdout.strip() == "C.UTF-8"


def test_run_never_uses_shell():
    # A shell metacharacter must be passed literally as an argument.
    r = runner.run(["echo", "a; echo injected"])
    assert r.stdout.strip() == "a; echo injected"


def test_empty_command_rejected():
    import pytest

    with pytest.raises(ValueError):
        runner.run([])
