"""Start a child process without letting it touch the MCP stdio channel.

Under the MCP stdio server (`SIMPLICIO_MCP=1`) fds 0/1 are the JSON-RPC stream: a child that inherits them can write into
it or swallow client input. There the child gets stdin=/dev/null and its stdout/stderr are captured and re-emitted through
Python's sys.stdout/sys.stderr (which `mcp_server._cli` already captures). In a terminal it is exactly subprocess.call."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from typing import Any

ENV_FLAG = "SIMPLICIO_MCP"


def under_mcp() -> bool:
    return os.environ.get(ENV_FLAG) == "1"


def run_child(argv: Sequence[Any], **kw: Any) -> int:
    """Run `argv` to completion and return its exit code. Extra keywords (cwd, env, timeout) go to subprocess."""
    if not under_mcp():
        return subprocess.call(argv, **kw)
    for k in ("stdin", "stdout", "stderr", "capture_output", "input"):
        kw.pop(k, None)
    # Temp files, not pipes: a pipe would keep run() waiting for any grandchild that inherited it (`(sleep 4 &)`).
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        rc = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err, **kw).returncode
        for f, sink in ((out, sys.stdout), (err, sys.stderr)):
            f.seek(0)
            text = f.read().decode("utf-8", errors="replace")  # explicit: the locale codec (cp1252 on Windows) would garble it
            if text:
                sink.write(text)
    return rc


def check_child(argv: Sequence[Any], **kw: Any) -> None:
    """`subprocess.run(argv, check=True)` through run_child: raises CalledProcessError on a non-zero exit."""
    rc = run_child(argv, **kw)
    if rc != 0:
        raise subprocess.CalledProcessError(rc, list(argv))
