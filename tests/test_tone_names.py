"""Ring tone names are literals in the application image; media.names patches them (#190).

A name written to the seed `up_common.sqlite` kept its stock name on a real unit, because the
ringtone menu shows strings from C_SRV_RING_TOUCH::SetRingFilePath instead. These pin the
generated patch: the expect bytes are the stock name padded to its room, the new bytes fit
the same room, and bad names are refused before anything is built.
"""

import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)

import helpers  # noqa: E402
import ringtones  # noqa: E402

BASE = 0x01000000


def edits(names):
    return ringtones.name_patch_spec("NAV", names)["variants"]["NAV"]["patches"]


def test_a_name_is_padded_to_its_slot_and_expects_the_stock_name():
    (e,) = edits({"ring1": "Piano"})
    assert int(e["addr"], 16) == 0x03063198
    assert bytes.fromhex(e["expect"]) == b"Alien\0\0\0"  # 7 characters of room + NUL
    assert bytes.fromhex(e["bytes"]) == b"Piano\0\0\0"


def test_every_slot_uses_its_full_room():
    for slot, (_, stock, room) in ringtones.APP_NAMES["NAV"]["slots"].items():
        (e,) = edits({slot: "x" * room})
        assert len(bytes.fromhex(e["bytes"])) == room + 1
        assert bytes.fromhex(e["bytes"]).endswith(b"\0"), "always NUL-terminated"
        assert bytes.fromhex(e["expect"]).startswith(stock.encode())


@pytest.mark.parametrize("name", ["Piano_riff", "", "Pianó"])
def test_a_name_that_does_not_fit_is_refused(name):
    with pytest.raises(SystemExit, match="must be 1-7 printable ASCII"):
        edits({"ring1": name})


def test_an_unknown_slot_or_unmapped_module_is_refused():
    with pytest.raises(SystemExit, match="names only apply"):
        edits({"ring6": "x"})
    with pytest.raises(SystemExit, match="only mapped for NAV"):
        ringtones.name_patch_spec("AUDIO_BT", {"ring1": "x"})


def test_the_generated_set_applies_through_patch_smeg(tmp_path):
    img = bytearray(helpers.make_image_with_build("5.43.A.R2", size=0x2064000))
    for e in edits({"ring1": "Piano", "ring3": "Custom_tone"}):
        off = int(e["addr"], 16) - BASE
        img[off : off + len(bytes.fromhex(e["expect"]))] = bytes.fromhex(e["expect"])
    src = tmp_path / "SMEG_PLUS_UPG"
    src.mkdir()
    helpers.build_package(str(src), variant="NAV", img=bytes(img))
    spec = tmp_path / "names.json"
    spec.write_text(
        json.dumps(ringtones.name_patch_spec("NAV", {"ring1": "Piano", "ring3": "Custom_tone"}))
    )
    out = tmp_path / "out"
    r = subprocess.run(
        [
            sys.executable,
            os.path.join(TOOLS, "patch_smeg.py"),
            "--src",
            str(src),
            "--out",
            str(out),
            "--patches",
            str(spec),
            "--only",
            "NAV",
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    patched = helpers.inflate_container((out / "NAV" / "AppBin" / "f_BigQuick.bin").read_bytes())
    assert patched[0x03063198 - BASE :].startswith(b"Piano\0\0\0")
    assert patched[0x030631C4 - BASE :].startswith(b"Custom_tone\0")
