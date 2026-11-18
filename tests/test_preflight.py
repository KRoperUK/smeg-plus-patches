"""Tests for the pre-flight check.

The point of this tool is that it fails loudly on the things that have cost car trips, so
the tests are about the failures it must catch rather than the happy path.
"""

import gzip
import io
import json
import os
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)


def up_common(last_source=None, names=None):
    names = names or ["Alien", "Blue_lemon"]
    t = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)  # noqa: SIM115  # closed on the next line; delete=False so sqlite can reopen it by name
    t.close()
    c = sqlite3.connect(t.name)
    c.execute(
        "create table UP_Keys (Section text, Name text, Idx int, IntValue int, StringValue text)"
    )
    for i, n in enumerate(names):
        c.execute("insert into UP_Keys values ('phone','Ringing_List',?,NULL,?)", (i, n))
    if last_source is not None:
        c.execute("insert into UP_Keys values ('supervisor','Last_Source',0,?,'')", (last_source,))
    c.commit()
    c.close()
    data = Path(t.name).read_bytes()
    os.unlink(t.name)
    return data


def make_pkg(tmp_path, last_source=None, user_data=False, folder="SMEG_PLUS_UPG"):
    """A minimal package.

    `folder` defaults to the name the updater hard-codes, because a `USER_DATA` payload is
    only read from `/bd0/SMEG_PLUS_UPG/NAV/USER_DATA` — a package built under any other name
    is a real, and silent, mistake. Pass something else to exercise that check.
    """
    pkg = tmp_path / folder
    files = {"Data_base/sqlite/up_common.sqlite": up_common(last_source)}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tf:
        for name, data in files.items():
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            ti.mtime = 0
            tf.addfile(ti, io.BytesIO(data))
    (pkg / "NAV").mkdir(parents=True)
    (pkg / "NAV" / "system.bin").write_bytes(gzip.compress(buf.getvalue(), 6))
    (pkg / "ctrl.bin").write_bytes(b"x")
    (pkg / "contract.dat").write_bytes(b"x")
    (pkg / "media.inf").write_bytes(b"VER:0\n")
    if user_data:
        import preflight

        d = pkg / "NAV" / "USER_DATA" / "user_data" / "sqlite"
        d.mkdir(parents=True)
        database = d / "up_common.sqlite"
        database.write_bytes(up_common(last_source))
        (d / "up_common.sqlite.inf").write_bytes(preflight.sqlite_inf(database.read_bytes()))
    return pkg


def run(pkg, *extra):
    return subprocess.run(
        [sys.executable, os.path.join(TOOLS, "preflight.py"), "--package", str(pkg), *extra],
        capture_output=True,
        text=True,
    )


def make_pkg_with_image(tmp_path, version):
    """A package whose application image carries a vendor build path, as the real ones do."""
    import helpers

    pkg = make_pkg(tmp_path)
    appbin = pkg / "NAV" / "AppBin"
    appbin.mkdir(parents=True, exist_ok=True)
    (appbin / "f_BigQuick.bin").write_bytes(
        helpers.pack_bigquick(helpers.make_image_with_build(version))
    )
    return pkg


def test_flags_a_source_that_is_not_a_real_source(tmp_path):
    """The exact mistake that cost a car trip: 4 is not a valid source."""
    r = run(make_pkg(tmp_path, last_source=4))
    out = r.stdout + r.stderr
    assert r.returncode != 0, "an invalid source must be a hard failure"
    assert "NOT a valid source" in out
    assert "AUX" in out, "it should name what the valid values are"


def test_accepts_a_real_source(tmp_path):
    r = run(make_pkg(tmp_path, last_source=7))
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert "= 7 (AUX)" in out


def test_seed_settings_carry_the_no_effect_note(tmp_path):
    """#254: a clean OK on seed Last_Source must say it does not reach the unit."""
    r = run(make_pkg(tmp_path, last_source=7))
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert "= 7 (AUX)" in out
    assert "ignores these values unless they arrive via USER_DATA" in out


def test_live_user_data_settings_carry_no_seed_note(tmp_path):
    """#254: the note belongs to the seed database, not to shipped USER_DATA."""
    r = run(make_pkg(tmp_path, last_source=7, user_data=True))
    out = r.stdout + r.stderr
    assert out.count("ignores these values unless they arrive via USER_DATA") == 1


def test_warns_about_a_user_data_payload(tmp_path):
    r = run(make_pkg(tmp_path, last_source=7, user_data=True))
    out = r.stdout + r.stderr
    assert "user partition" in out
    assert "presets" in out, "it should say what is at risk"
    assert "inf matches the database" in out


def test_refuses_user_data_without_a_crc_sidecar(tmp_path):
    pkg = make_pkg(tmp_path, last_source=7, user_data=True)
    (pkg / "NAV" / "USER_DATA" / "user_data" / "sqlite" / "up_common.sqlite.inf").unlink()

    r = run(pkg)

    assert r.returncode != 0
    assert "has no CRC sidecar" in (r.stdout + r.stderr)


def test_refuses_a_stale_user_data_crc_sidecar(tmp_path):
    pkg = make_pkg(tmp_path, last_source=7, user_data=True)
    sidecar = pkg / "NAV" / "USER_DATA" / "user_data" / "sqlite" / "up_common.sqlite.inf"
    sidecar.write_bytes(b"CRC32: 0\r\n")

    r = run(pkg)

    assert r.returncode != 0
    assert "does not match the database" in (r.stdout + r.stderr)


def test_says_what_it_does_not_know(tmp_path):
    """The unknowns are where the car trips went, so they must be printed."""
    r = run(make_pkg(tmp_path, last_source=7))
    out = r.stdout + r.stderr
    assert "merge" in out and "replace" in out or "cannot be settled" in out


def test_json_output_is_parseable(tmp_path):
    r = run(make_pkg(tmp_path, last_source=4), "--json")
    data = json.loads(r.stdout)
    assert data["problems"] >= 1
    assert any(row["level"] == "bad" for row in data["rows"])


# --- what the firmware version means for the patches --------------------------


def test_reports_the_firmware_version(tmp_path):
    """Every patch address belongs to one version, so say which one this package carries."""
    r = run(make_pkg_with_image(tmp_path, "5.43.A.R2"))
    assert "5.43.A.R2" in (r.stdout + r.stderr)


def test_names_the_version_even_when_it_is_not_the_expected_one(tmp_path):
    r = run(make_pkg_with_image(tmp_path, "5.42.B.R4"))
    assert "5.42.B.R4" in (r.stdout + r.stderr)


def test_says_when_the_version_cannot_be_determined(tmp_path):
    r = run(make_pkg(tmp_path, last_source=7))  # this fixture has no application image
    out = r.stdout + r.stderr
    assert "cannot tell the version" in out, "an unknown must be printed, not omitted"


def test_warns_that_the_payload_directory_must_arrive_lowercase(tmp_path):
    """The trap that made three flashes do nothing: SQLITE vs sqlite, see docs/FLASHING.md."""
    r = run(make_pkg(tmp_path, last_source=7, user_data=True))
    out = r.stdout + r.stderr
    assert "lowercase 'sqlite'" in out
    assert "long-filename" in out, "it should say why it happens"


def test_a_missing_package_is_a_clean_error(tmp_path):
    r = run(tmp_path / "nope")
    assert r.returncode != 0
    assert "no such package" in (r.stdout + r.stderr)


def test_refuses_a_user_data_payload_in_a_wrongly_named_folder(tmp_path):
    """The updater does not search for the payload — it checks one hard-coded path.

    `C_UPGRADE::UpgradeTask` calls `IsDirExist("/bd0/SMEG_PLUS_UPG/NAV/USER_DATA")` and skips
    the copy when it is not there, while the rest of the update succeeds normally. That is
    indistinguishable from a setting having had no effect, so it has to fail the build rather
    than be discovered on a car.
    """
    r = run(make_pkg(tmp_path, last_source=7, user_data=True, folder="SMEG_PLUS_UPG_auxdefault"))

    assert r.returncode != 0
    out = r.stdout + r.stderr
    assert "IGNORED" in out
    assert "SMEG_PLUS_UPG_auxdefault" in out, "it should name the offending folder"
    assert "/bd0/SMEG_PLUS_UPG/NAV/USER_DATA" in out, "it should name the path the unit uses"


def test_accepts_a_user_data_payload_in_the_right_folder(tmp_path):
    """The correctly named folder must not trip the check."""
    r = run(make_pkg(tmp_path, last_source=7, user_data=True))

    out = r.stdout + r.stderr
    assert "IGNORED" not in out
    assert "user partition" in out, "the data-loss warning still applies"


def test_folder_name_check_only_applies_to_a_payload(tmp_path):
    """A package with no payload has nothing to lose, so the name does not matter."""
    r = run(make_pkg(tmp_path, last_source=7, folder="whatever"))

    out = r.stdout + r.stderr
    assert "IGNORED" not in out
    assert "no payload" in out


def test_refuses_a_user_data_payload_for_a_non_nav_module(tmp_path):
    """The hard-coded path names NAV, so an AUDIO_BT payload is never read."""
    pkg = make_pkg(tmp_path, last_source=7, user_data=True)
    # move the payload under a module the hard-coded path cannot reach
    (pkg / "AUDIO_BT").mkdir(parents=True, exist_ok=True)
    (pkg / "NAV" / "USER_DATA").rename(pkg / "AUDIO_BT" / "USER_DATA")
    (pkg / "AUDIO_BT" / "system.bin").write_bytes((pkg / "NAV" / "system.bin").read_bytes())

    r = run(pkg, "--module", "AUDIO_BT")

    assert r.returncode != 0
    assert "not read at all" in (r.stdout + r.stderr)


def test_a_stock_site_shorter_than_its_patch_is_reported_as_stock():
    """IsAUXSRCAvailable's patch is 8 bytes over 4 stock bytes; stock must not read as unknown."""
    import preflight

    img = bytearray(0x1300000)
    off = 0x02247858 - 0x01000000
    img[off : off + 8] = bytes.fromhex("9421ffa07c0802a6")  # stock stwu, then the next insn
    rep = preflight.Report()
    preflight.check_patches(rep, bytes(img), "NAV")
    rows = [m for _, area, m in rep.rows if "IsAUXSRCAvailable" in m or "0x02247858" in m]
    assert rows == ["stock    C_HMI_AUDIO_APP_BASE::IsAUXSRCAvailable -> return true"]


# ------------------------------------------------------- tranche-2 #255 dedupe
def test_known_patches_come_from_the_patch_sets():
    """The table must cover every module the patch sets describe (#255)."""
    import preflight

    assert set(preflight.KNOWN_PATCHES) >= {"NAV", "AUDIO_BT", "AUDIO_BT_256"}
    nav_addrs = {addr for addr, _, _, _ in preflight.KNOWN_PATCHES["NAV"]}
    assert 0x02247858 in nav_addrs and 0x010346D0 in nav_addrs
    assert any("AUX" in why for _, _, _, why in preflight.KNOWN_PATCHES["AUDIO_BT_256"]), (
        "AUDIO_BT_256 rows must not be absent"
    )


def test_competing_patches_at_one_address_read_as_patched():
    """diagnostic-logging and diagnostic-logsink share 0x010346d0 with different bytes."""
    import preflight

    img = bytearray(0x1300000)
    off = 0x010346D0 - 0x01000000
    img[off : off + 4] = bytes.fromhex("4b4503c4")  # the logsink form
    rep = preflight.Report()
    present = preflight.check_patches(rep, bytes(img), "NAV")
    assert len(present) == 1
    assert not any("0x010346d0" in m for _, _, m in rep.rows if "unrecognised" in m)


def test_read_module_finds_the_alternate_offset_stream(tmp_path):
    """An image whose stream sits at 0x800 must not report UNKNOWN firmware (#255)."""
    import zlib as _zlib

    import helpers
    import preflight

    img = helpers.make_image()
    raw = b"\x00" * 0x800 + _zlib.compress(bytes(img))
    pkg = tmp_path / "SMEG_PLUS_UPG"
    appbin = pkg / "NAV" / "AppBin"
    appbin.mkdir(parents=True)
    (appbin / "f_BigQuick.bin").write_bytes(raw)

    got, _, err = preflight.read_module(str(pkg), "NAV")

    assert got == bytes(img)
    assert err is None


def test_load_known_patches_reads_a_single_file(tmp_path):
    import json as _json

    import preflight

    spec = {
        "name": "custom",
        "variants": {
            "NAV": {
                "app_image": "NAV/AppBin/f_BigQuick.bin",
                "inf": "NAV/AppBin/f_BigQuick.bin.inf",
                "smeg_inf": "NAV/smeg.inf",
                "ctrl": "NAV_ctrl.bin",
                "base": "0x01000000",
                "firmware": "9.99",
                "patches": [
                    {
                        "addr": "0x01000100",
                        "expect": "00",
                        "bytes": "01",
                        "why": "custom probe",
                    }
                ],
            }
        },
    }
    p = tmp_path / "custom.json"
    p.write_text(_json.dumps(spec))

    table = preflight.load_known_patches([str(p)])

    assert table == {"NAV": [(0x01000100, "00", "01", "custom probe")]}


# --- unreadable media is a finding, not an empty partition (#237) --------------


def test_corrupt_system_bin_is_reported_not_silent(tmp_path):
    """A garbage system.bin used to pass the final gate with no finding."""
    pkg = make_pkg(tmp_path, last_source=4)
    (pkg / "NAV" / "system.bin").write_bytes(b"this is not a gzip'd tar")
    r = run(pkg, "--json")
    data = json.loads(r.stdout)
    unknowns = [row for row in data["rows"] if row["level"] == "unknown"]
    assert any("system.bin" in row["message"] for row in unknowns), data["rows"]


def test_corrupt_settings_db_is_reported_not_silent(tmp_path):
    """A corrupt up_common.sqlite used to skip the Last_Source check silently."""
    import io as _io
    import tarfile as _tarfile

    pkg = make_pkg(tmp_path, last_source=4)
    buf = _io.BytesIO()
    with _tarfile.open(fileobj=buf, mode="w", format=_tarfile.GNU_FORMAT) as tf:
        blob = b"this is not sqlite"
        ti = _tarfile.TarInfo("Data_base/sqlite/up_common.sqlite")
        ti.size = len(blob)
        ti.mtime = 0
        tf.addfile(ti, _io.BytesIO(blob))
    import gzip as _gzip

    (pkg / "NAV" / "system.bin").write_bytes(_gzip.compress(buf.getvalue(), 6))
    r = run(pkg, "--json")
    data = json.loads(r.stdout)
    unknowns = [row for row in data["rows"] if row["level"] == "unknown"]
    assert any("up_common.sqlite" in row["message"] for row in unknowns), data["rows"]
