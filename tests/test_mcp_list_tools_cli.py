"""``python -m agentmemory.mcp_server --list-tools`` must fail loudly.

When the MCP SDK can't be imported (or is an incompatible 2.x release),
the inspection flag has to exit non-zero with an actionable stderr
message instead of a bare traceback or a silent, empty success.

Each case runs in a subprocess so the broken SDK never leaks into this
interpreter's ``sys.modules``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="brainctl[mcp] required for stdio server tests")


def _run_list_tools(tmp_path: Path, prelude: str = "") -> subprocess.CompletedProcess:
    script = prelude + textwrap.dedent(
        """
        import runpy, sys
        sys.argv = ["mcp_server", "--list-tools"]
        runpy.run_module("agentmemory.mcp_server", run_name="__main__", alter_sys=True)
        """
    )
    env = dict(os.environ)
    env["BRAINCTL_HOME"] = str(tmp_path / "home")
    env["BRAINCTL_DB"] = str(tmp_path / "brain.db")
    env.pop("BRAINCTL_ALLOWED_TOOLS", None)
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        timeout=120,
    )


def test_list_tools_prints_visible_surface(tmp_path: Path) -> None:
    proc = _run_list_tools(tmp_path)
    assert proc.returncode == 0, proc.stderr
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines, "--list-tools printed nothing"
    assert any(ln.strip().startswith("memory_add:") for ln in lines)


def test_list_tools_fails_loudly_when_mcp_is_missing(tmp_path: Path) -> None:
    prelude = textwrap.dedent(
        """
        import sys

        class _BlockMcp:
            def find_spec(self, name, path=None, target=None):
                if name == "mcp" or name.startswith("mcp."):
                    raise ModuleNotFoundError(f"No module named {name!r}", name=name)

        sys.meta_path.insert(0, _BlockMcp())
        """
    )
    proc = _run_list_tools(tmp_path, prelude)
    assert proc.returncode != 0
    assert proc.stdout == ""
    assert "the MCP SDK could not be loaded" in proc.stderr
    assert "No module named 'mcp'" in proc.stderr
    assert "pip install 'brainctl[mcp]'" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_list_tools_fails_loudly_on_incompatible_sdk(tmp_path: Path) -> None:
    # Minimal stand-in for mcp 2.x: the modules import, but the low-level
    # Server has no list_tools()/call_tool() decorators.
    fake = tmp_path / "fake_sdk" / "mcp"
    (fake / "server").mkdir(parents=True)
    (fake / "__init__.py").write_text("")
    (fake / "server" / "__init__.py").write_text(
        "class Server:\n    def __init__(self, name):\n        self.name = name\n"
    )
    (fake / "server" / "stdio.py").write_text("def stdio_server():\n    raise NotImplementedError\n")
    (fake / "types.py").write_text(
        "class Tool:\n"
        "    def __init__(self, **kw):\n"
        "        self.__dict__.update(kw)\n"
        "class TextContent(Tool):\n"
        "    pass\n"
    )
    prelude = f"import sys\nsys.path.insert(0, {str(fake.parent)!r})\n"
    proc = _run_list_tools(tmp_path, prelude)
    assert proc.returncode != 0
    assert proc.stdout == ""
    assert "the MCP SDK could not be loaded" in proc.stderr
    assert "mcp 2.x" in proc.stderr
    assert "Traceback" not in proc.stderr
