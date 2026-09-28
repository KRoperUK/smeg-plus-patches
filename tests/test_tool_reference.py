"""docs/TOOLS.md is generated from the tools; these keep it complete (#199).

The hand-written tool tables drifted (one was missing 14 of 31 tools). The page's --help
bodies are not compared exactly, because argparse formats them differently across Python
versions; the set of tools, their groups and their summaries are.
"""

import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
sys.path.insert(0, TOOLS)

import tool_reference  # noqa: E402

CLI_TOOLS, _ = tool_reference.discover()


def test_the_page_lists_every_tool_with_its_current_summary():
    assert tool_reference.check() == []


def test_every_tool_is_in_a_group():
    assert tool_reference.ungrouped(CLI_TOOLS) == []


@pytest.mark.parametrize("name", CLI_TOOLS)
def test_every_tool_answers_help(name):
    if name == "ppcdis":
        pytest.importorskip("capstone")
    r = subprocess.run(
        [sys.executable, os.path.join(TOOLS, name + ".py"), "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_new_tool_without_a_group_is_reported(tmp_path, monkeypatch):
    (tmp_path / "brand_new.py").write_text(
        '"""Does something new."""\nif __name__ == "__main__":\n    pass\n'
    )
    monkeypatch.setattr(tool_reference, "TOOLS", tmp_path)
    problems = tool_reference.check()
    assert any("brand_new.py is not in any group" in p for p in problems)
    assert any("brand_new.py is missing from docs/TOOLS.md" in p for p in problems)
