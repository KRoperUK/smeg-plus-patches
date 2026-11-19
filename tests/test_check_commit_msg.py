"""Tests for the Conventional Commits gate.

The repo squash-merges, so the PR title becomes the commit on `main` and drives
Release Please. A title that does not parse silently produces no release, which is
why `check_commit_msg.py` gates releases — yet nothing in `tests/` referenced it.
"""

import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
sys.path.insert(0, TOOLS)

import check_commit_msg as cm  # noqa: E402


@pytest.mark.parametrize(
    "text",
    [
        "feat: always offer AUX first in the SRC cycle",
        "fix: keep Studio firmware guard and re-seal build output",
        "fix(media): keep SIZE_1/2/4 deltas when replacing a tone",
        "docs!: rename the project to smeg-plus-patches",
        "fix!: drop falsified sets from the build manifests",
        "ci: pin the PR-title check to the same ruff as the hook",
        "feat: always offer AUX first\n\nBREAKING CHANGE: the SRC cycle starts at AUX",
        "Merge pull request #266 from KRoperUK/fix/tranche-3-smeg-plus-patches",
    ],
)
def test_valid_messages_pass(text):
    assert cm.check(text) == []


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("add a thing", "does not look like"),
        ("wip: a thing", "unknown type"),
        ("feat: Always offer AUX first", "capital"),
        ("feat: always offer AUX first.", "full stop"),
        ("", "empty"),
        ("feat: " + "x" * 200, "keep it under"),
    ],
)
def test_invalid_messages_fail_with_a_hint(text, fragment):
    problems = cm.check(text)
    assert problems, text
    assert any(fragment in p for p in problems), problems


def test_title_form_accepts_a_good_title():
    r = subprocess.run(
        [
            sys.executable,
            os.path.join(TOOLS, "check_commit_msg.py"),
            "--title",
            "fix: catch VINs in the PII guard",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr


def test_title_form_rejects_a_bad_title():
    r = subprocess.run(
        [sys.executable, os.path.join(TOOLS, "check_commit_msg.py"), "--title", "Updated stuff"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 1
    assert "Conventional Commits" in r.stderr


def test_hook_form_reads_a_message_file(tmp_path):
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("test: cover check_commit_msg, unpack and --help smoke\n")
    r = subprocess.run(
        [sys.executable, os.path.join(TOOLS, "check_commit_msg.py"), str(msg)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
