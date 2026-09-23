"""Tests for the personal-data guard.

A guard that cries wolf gets disabled, and then it protects nothing — so these cover both
directions: what it must catch, and what it must leave alone. The last test is the one that
matters most, because it checks the repository against itself.

The sample values are assembled from fragments rather than written whole. That is not
cheating the guard: a constructed fixture is exactly what this file should contain, and the
hook exists to catch data pasted in from the real world. Writing them whole would make this
file fail its own test — which is how the fragments were found.
"""

import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import check_no_pii  # noqa: E402

# Ofcom's reserved drama range, and the example postcode. Safe to test with, unsafe to
# commit — hence the split.
MOBILE_UK = "07700 900" + "123"
MOBILE_INTL = "+44 7700 900" + "123"
EMAIL = "someone@" + "personal.co.uk"
POSTCODE = "SW1A" + " 1AA"
NI = "AB" + "123456C"


def scan_text(tmp_path, text, name="probe.txt"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return [(lineno, what, hit) for lineno, what, hit in check_no_pii.scan(str(path))]


@pytest.mark.parametrize(
    "line, expected",
    [
        ("ring me on " + MOBILE_UK, "UK mobile number"),
        ("ring " + MOBILE_INTL, "UK mobile number"),
        ("send it to " + EMAIL, "email address"),
        ("the car was at " + POSTCODE, "UK postcode"),
        ("NI number " + NI + " on file", "NI number"),
    ],
)
def test_catches_personal_data(tmp_path, line, expected):
    hits = scan_text(tmp_path, line + "\n")
    assert expected in [what for _, what, _ in hits], hits


@pytest.mark.parametrize(
    "line",
    [
        "the patch sits at 0x012739dc, expect 38600001",
        "GetUserDataDir is 0x0105ae44 in the NAV image",
        "python3 tools/patch_smeg.py --src SMEG_PLUS_UPG --out overlay",
        "released 2023-05-03 as CD 26482",
        "co-authored-by: CommandCodeBot <noreply@commandcode.ai>",
        "mail the maintainer at someone@example.com",
    ],
)
def test_leaves_ordinary_lines_alone(tmp_path, line):
    assert scan_text(tmp_path, line + "\n") == []


def test_marker_suppresses_a_line(tmp_path):
    assert scan_text(tmp_path, "example value " + MOBILE_UK + "  # pii-ok\n") == []
    # ...but only that line
    hits = scan_text(tmp_path, "example value " + MOBILE_UK + "\n")
    assert [what for _, what, _ in hits] == ["UK mobile number"]


def test_binary_suffixes_are_skipped(tmp_path):
    assert scan_text(tmp_path, MOBILE_UK + "\n", name="app.bin") == []


def test_the_repository_itself_is_clean():
    """The guard is only worth having if this tree passes it."""
    listed = ""
    try:
        listed = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    findings = [
        (path, lineno, what, hit)
        for path in listed.split()
        for lineno, what, hit in check_no_pii.scan(os.path.join(ROOT, path))
    ]
    assert not findings, findings
