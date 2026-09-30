"""`aux-no-idle-mute` drops the AUX no-signal mute from the radio mute decision.

`C_MODULE_AUDIO+0x168` is one of four terms in `RadioMuteManager`'s DSP mute decision, and the
only function that reads that offset for anything but a spy line. The edit removes that one
term, so the mistake to guard against is not a wrong byte but the wrong *term*: a `nop` two
instructions above it would disarm the system mute, and one two instructions below would leave
the timed mute stuck on. Neither check needs firmware:

  1. `expect` must decode to `bne cr7, <negative>` — the branch to `li r31,1`, the "muted"
   result — and `bytes` to `nop`, at the same offset inside `RadioMuteManager` on all three
   builds, and
  2. the shipped definition still applies through `patch_smeg.py` and rebuilds the CRC
     cascade, against a synthetic image carrying the expect bytes at the patch address.

What the edit *does* is executed against the real image in `tests/test_firmware_nav.py` and
`tests/test_firmware_audio_bt.py`; it cannot be checked here without vendor firmware.
"""

import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)

import helpers  # noqa: E402

PATCH_FILE = os.path.join(ROOT, "patches", "aux-no-idle-mute.json")
# C_MODULE_AUDIO::RadioMuteManager, from each build's own symbol map (system.bin,
# Application/PKG/abs_symbols_base.txt.gz). AUDIO_BT and AUDIO_BT_256 ship the same map.
FUNCTION = {"NAV": 0x013B3C5C, "AUDIO_BT": 0x013B3B04, "AUDIO_BT_256": 0x013B3B04}
GATE_OFFSET = 0x1A0  # the +0x168 test
MUTED_OFFSET = 0x6C  # `li r31,1` — what the branch goes to, and the only place it may go
NOP = 0x60000000


def spec():
    return json.loads(Path(PATCH_FILE).read_text())


def edits(module):
    return spec()["variants"][module]["patches"]


def word(hexstr):
    return struct.unpack(">I", bytes.fromhex(hexstr))[0]


def variants():
    return sorted(spec()["variants"])


@pytest.mark.parametrize("module", variants())
def test_the_edit_sits_on_the_aux_no_signal_term(module):
    """One instruction at RadioMuteManager+0x1a0 on every build."""
    assert len(edits(module)) == 1, "this set is deliberately a single instruction"
    addr = int(edits(module)[0]["addr"], 16)
    assert addr - FUNCTION[module] == GATE_OFFSET


@pytest.mark.parametrize("module", variants())
def test_expect_is_a_conditional_branch_to_the_muted_result(module):
    """`expect` is `bne cr7, li r31,1` — a branch whose taken path means "muted".

    Opcode 16 is `bc`. BO 5 is `bne`, and BI 30 is CR7's EQ bit, so the branch is taken when
    the byte at `+0x168` is non-zero. The displacement must land on the function's `li r31,1`,
    which is what makes this the AUX term and not one of the three beside it.
    """
    addr = int(edits(module)[0]["addr"], 16)
    op, bo, bi, disp = (
        word(edits(module)[0]["expect"]) >> 26,
        (word(edits(module)[0]["expect"]) >> 21) & 0x1F,
        (word(edits(module)[0]["expect"]) >> 16) & 0x1F,
        word(edits(module)[0]["expect"]) & 0xFFFC,
    )
    assert op == 16, "expect should be a conditional branch (bc, opcode 16)"
    assert bo == 5 and bi == 30, "expect should be `bne cr7`"
    if disp & 0x8000:
        disp -= 0x10000
    assert disp < 0, "the branch goes backwards, to the `li r31,1` above it"
    assert addr + disp == FUNCTION[module] + MUTED_OFFSET


@pytest.mark.parametrize("module", variants())
def test_bytes_are_a_nop(module):
    assert word(edits(module)[0]["bytes"]) == NOP
    assert edits(module)[0]["disasm"].strip() == "nop"


@pytest.mark.parametrize("module", variants())
def test_shipped_definition_applies_and_cascades(module, tmp_path):
    """End-to-end: the shipped patches/aux-no-idle-mute.json applies through patch_smeg.py."""
    off = int(edits(module)[0]["addr"], 16) - 0x01000000
    expect = bytes.fromhex(edits(module)[0]["expect"])
    img = bytearray(helpers.make_image_with_build("5.43.A.R2", size=0x400000))
    img[off : off + len(expect)] = expect

    src = tmp_path / "SMEG_PLUS_UPG"
    src.mkdir()
    helpers.build_package(str(src), variant=module, img=bytes(img))

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
            PATCH_FILE,
            "--only",
            module,
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr

    patched = helpers.inflate_container((out / module / "AppBin" / "f_BigQuick.bin").read_bytes())
    assert patched[off : off + len(expect)].hex() == edits(module)[0]["bytes"], "edit did not land"
