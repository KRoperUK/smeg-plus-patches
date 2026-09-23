"""Tests for the package checksum audit.

Every check here has a case that makes it fail. An audit that only ever passes is worse than
no audit, because it invites someone to trust a package that will be refused by the unit.
"""

import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)

import helpers  # noqa: E402
import verify_package  # noqa: E402


def run(*args):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True)


@pytest.fixture()
def pkg(tmp_path):
    p = tmp_path / "SMEG_PLUS_UPG"
    p.mkdir()
    info = helpers.build_package(str(p), variant="NAV")
    return p, info


# --------------------------------------------------------------- the happy path


def test_a_consistent_package_has_no_problems(pkg):
    p, _ = pkg
    assert verify_package.audit(str(p)) == []


def test_the_cli_passes_a_consistent_package(pkg):
    p, _ = pkg
    r = run(os.path.join(TOOLS, "verify_package.py"), "--package", str(p))
    assert r.returncode == 0, r.stdout
    assert "consistent" in r.stdout


# ------------------------------------------------------------- each failure mode


def test_a_file_changed_after_the_inf_was_written_is_caught(pkg):
    """The failure this exists for: the bytes and the record disagree."""
    p, info = pkg
    with open(info["app_image"], "ab") as fh:
        fh.write(b"\x00")
    problems = verify_package.audit(str(p))
    assert any(x["kind"] == "inf-sidecar" for x in problems)


def test_a_manifest_that_lost_a_crc_is_caught(pkg):
    p, info = pkg
    with open(info["ctrl"], "wb") as fh:
        fh.write(b"\x00" * os.path.getsize(info["ctrl"]))
    problems = verify_package.audit(str(p))
    assert any("does not record the CRC" in x["detail"] for x in problems)


def test_a_root_manifest_that_lost_a_crc_is_caught(pkg):
    p, info = pkg
    root_manifest = p / "ctrl.bin"
    with open(str(root_manifest), "wb") as fh:
        fh.write(b"\x00" * os.path.getsize(str(root_manifest)))
    problems = verify_package.audit(str(p))
    assert any(x["where"] == "ctrl.bin" for x in problems)


def test_a_missing_image_is_caught(tmp_path):
    p = tmp_path / "SMEG_PLUS_UPG"
    p.mkdir()
    info = helpers.build_package(str(p), variant="NAV")
    os.remove(info["app_image"])
    problems = verify_package.audit(str(p))
    assert any("does not exist" in x["detail"] for x in problems)


def test_a_missing_root_manifest_is_caught(tmp_path):
    p = tmp_path / "SMEG_PLUS_UPG"
    p.mkdir()
    helpers.build_package(str(p), variant="NAV")
    os.remove(str(p / "ctrl.bin"))
    problems = verify_package.audit(str(p))
    assert any(x["where"] == "ctrl.bin" and "missing" in x["detail"] for x in problems)


def test_a_wrong_smeg_inf_is_caught(pkg):
    p, info = pkg
    with open(info["smeg_inf"], "wb") as fh:
        fh.write(b"BSP_CRC32: 0 \r\nBIGQUICK_CRC32: 12345 \r\nVER: X \r\nGUI_VER:00.00 \r\n")
    problems = verify_package.audit(str(p))
    assert any(x["kind"] == "smeg-inf" for x in problems)


def test_a_smeg_inf_without_the_field_is_caught(pkg):
    p, info = pkg
    with open(info["smeg_inf"], "wb") as fh:
        fh.write(b"VER: X \r\nGUI_VER:00.00 \r\n")
    problems = verify_package.audit(str(p))
    assert any("no BIGQUICK_CRC32 field" in x["detail"] for x in problems)


# ------------------------------------------------------------- the tricky bit


def test_smeg_inf_is_not_mistaken_for_a_sidecar(pkg):
    """`smeg.inf` contains BSP_CRC32, whose text ends in "CRC32: 0".

    A naive substring match reads that as a sidecar CRC32 of 0 describing a file called
    `smeg`, which does not exist - so a perfectly good package would report two failures. The
    field has to match as a bare key.
    """
    p, info = pkg
    assert verify_package.read_field(info["smeg_inf"], verify_package.INF_SIDECAR_RE) is None
    assert verify_package.audit(str(p)) == []


def test_the_cli_reports_a_bad_package_and_exits_non_zero(pkg):
    p, info = pkg
    with open(info["app_image"], "ab") as fh:
        fh.write(b"\x00")
    r = run(os.path.join(TOOLS, "verify_package.py"), "--package", str(p))
    assert r.returncode == 1
    assert "do not flash this package" in r.stdout


def test_json_output_is_parseable(pkg):
    p, info = pkg
    with open(info["app_image"], "ab") as fh:
        fh.write(b"\x00")
    r = run(os.path.join(TOOLS, "verify_package.py"), "--package", str(p), "--json")
    assert r.returncode == 1
    doc = json.loads(r.stdout)
    assert doc["problems"] and doc["summary"]["modules"] == ["NAV"]


def test_a_package_with_no_modules_is_not_reported_as_consistent(tmp_path):
    """Nothing to check is not the same as nothing wrong."""
    p = tmp_path / "SMEG_PLUS_UPG"
    p.mkdir()
    r = run(os.path.join(TOOLS, "verify_package.py"), "--package", str(p))
    assert r.returncode == 1
    assert "nothing to audit" in r.stdout
