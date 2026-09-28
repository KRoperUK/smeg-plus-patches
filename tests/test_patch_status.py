"""Patch status lives in `patches/*.json`; the docs' tables are generated from it (#198).

The status used to be restated by hand in several pages and drifted. These tests make CI fail
when a generated block is stale, and when a patch set has no valid status.
"""

import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
sys.path.insert(0, TOOLS)

import patch_status  # noqa: E402


def test_the_generated_blocks_are_up_to_date():
    r = subprocess.run(
        [sys.executable, os.path.join(TOOLS, "patch_status.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_every_patch_set_has_a_known_state():
    entries = patch_status.load()
    assert entries and all(s["state"] in patch_status.STATES for _, _, s in entries)


def test_a_patch_without_a_status_is_refused(tmp_path, monkeypatch):
    (tmp_path / "x.json").write_text(json.dumps({"name": "x", "description": "d"}))
    monkeypatch.setattr(patch_status, "PATCHES", tmp_path)
    with pytest.raises(SystemExit, match="needs"):
        patch_status.load()


def test_a_stale_block_is_detected_and_rewritten(tmp_path, monkeypatch):
    page = tmp_path / "p.md"
    page.write_text("x\n<!-- patch-status:table -->\nold\n<!-- /patch-status:table -->\ny\n")
    monkeypatch.setattr(patch_status, "TARGETS", {"table": page})
    assert patch_status.main(["--check"]) == 1
    assert patch_status.main([]) == 0
    assert "| file | what it changes | status |" in page.read_text()
    assert patch_status.main(["--check"]) == 0
