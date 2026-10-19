"""Safe execution of read-only system commands.

Commands are always passed as argument lists (never through a shell), with a
timeout and a C locale so their output can be parsed reliably.  A missing
executable or a timeout is reported in the result instead of raising, so the
callers can degrade gracefully.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Sequence

DEFAULT_TIMEOUT = 15


@dataclass(frozen=True)
class CommandResult:
    args: tuple
    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    missing: bool = False
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.missing and not self.timed_out


Runner = Callable[[Sequence[str], float], CommandResult]


def run(args: Sequence[str], timeout: float = DEFAULT_TIMEOUT) -> CommandResult:
    """Run *args* and capture its output. Never raises for expected failures."""
    args = tuple(args)
    if not args:
        raise ValueError("empty command")
    if shutil.which(args[0]) is None:
        return CommandResult(args, None, missing=True)
    env = dict(os.environ, LC_ALL="C.UTF-8", LANG="C.UTF-8")
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            env=env,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(args, None, _text(exc.stdout), _text(exc.stderr), timed_out=True)
    except OSError as exc:  # e.g. permission denied on the executable
        return CommandResult(args, None, "", str(exc), missing=True)
    return CommandResult(args, proc.returncode, proc.stdout, proc.stderr)


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value
