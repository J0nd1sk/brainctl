"""Belief-collapse mechanics ship inside the ``agentmemory`` package.

``collapse_mechanics`` used to live at the repo root: the CLI's
``from agentmemory.collapse_mechanics import ...`` raised
ModuleNotFoundError, and the MCP tools only worked when the checkout sat
at ``~/agentmemory`` (they pushed that onto ``sys.path``). These tests pin
the packaged location and run each entry point against a temp DB with
HOME pointed somewhere that has no ``agentmemory`` checkout.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _env(db_path: Path, home: Path) -> dict:
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["BRAINCTL_HOME"] = str(home / ".brainctl-home")
    env["BRAINCTL_DB"] = str(db_path)
    env.pop("BRAIN_DB", None)
    return env


def test_module_lives_in_the_package() -> None:
    import agentmemory
    from agentmemory import collapse_mechanics

    pkg_dir = Path(agentmemory.__file__).resolve().parent
    assert Path(collapse_mechanics.__file__).resolve().parent == pkg_dir
    for name in ("collapse_stats", "list_collapse_events", "force_collapse"):
        assert callable(getattr(collapse_mechanics, name))


@pytest.mark.parametrize(
    "argv",
    [["collapse-stats", "--json"], ["collapse-log", "--json"]],
)
def test_cli_collapse_commands_import_and_run(cli_db, tmp_path, argv) -> None:
    home = tmp_path / "home"
    home.mkdir()
    proc = subprocess.run(
        [sys.executable, "-m", "agentmemory.cli", *argv],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(home),
        env=_env(Path(cli_db), home),
    )
    assert proc.returncode == 0, proc.stderr
    assert "ModuleNotFoundError" not in proc.stderr
    payload = json.loads(proc.stdout)
    if argv[0] == "collapse-stats":
        assert payload["total_collapses"] == 0
    else:
        assert payload == []


def test_mcp_collapse_tools_resolve_packaged_module(cli_db, tmp_path, monkeypatch) -> None:
    pytest.importorskip("mcp", reason="brainctl[mcp] required for MCP tool tests")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("BRAINCTL_DB", str(cli_db))
    monkeypatch.delenv("BRAIN_DB", raising=False)

    from agentmemory import mcp_tools_beliefs

    stats = mcp_tools_beliefs.tool_collapse_stats()
    assert stats["ok"] is True, stats
    assert stats["total_collapses"] == 0

    log = mcp_tools_beliefs.tool_collapse_log()
    assert log == {"ok": True, "count": 0, "events": []}

    from agentmemory import mcp_server

    result = mcp_server.tool_belief_collapse(agent_id="test-agent", action="stats")
    assert "import failed" not in str(result.get("error", "")), result
    assert result.get("total_collapses") == 0, result
