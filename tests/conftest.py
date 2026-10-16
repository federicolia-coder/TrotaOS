"""Pytest configuration: make the application packages importable from the
source tree and provide a fake command runner."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for app_dir in sorted((ROOT / "applications").iterdir()):
    if app_dir.is_dir():
        sys.path.insert(0, str(app_dir))

from trota_common.runner import CommandResult  # noqa: E402


class FakeRunner:
    """Maps a command prefix (tuple) to a CommandResult; records calls."""

    def __init__(self, responses=None):
        self.responses = dict(responses or {})
        self.calls = []

    def __call__(self, args, timeout=None):
        args = tuple(args)
        self.calls.append(args)
        for n in range(len(args), 0, -1):
            if args[:n] in self.responses:
                r = self.responses[args[:n]]
                return r if isinstance(r, CommandResult) else CommandResult(args, 0, r)
        return CommandResult(args, None, missing=True)


def ok(stdout="", stderr=""):
    return CommandResult((), 0, stdout, stderr)


def fail(code=1, stdout="", stderr=""):
    return CommandResult((), code, stdout, stderr)


@pytest.fixture
def fake_runner():
    return FakeRunner


@pytest.fixture
def root_dir():
    return ROOT
