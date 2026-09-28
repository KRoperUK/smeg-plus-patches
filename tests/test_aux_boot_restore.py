"""`aux-boot-restore` lets AUX's source request take part in C_MGR_SRC's boot restore.

Two edits. `AddRequest` skips the ScheduledInit/restore block for a request whose PrOnly
byte is set, and the AUX input handler sets it by calling `ActivateSource(aux, true)`;
`StartUp` restores Last_Source_Priority, which has to equal AUX's 20 for the comparison to
match. Neither check needs firmware:

  1. each `expect` and `bytes` decodes to the instruction the definition claims, so a wrong
     branch encoding or register fails here rather than on a car, and
  2. the shipped definition applies through `patch_smeg.py`, against a synthetic image
     carrying the expect bytes at both addresses.
"""

import json
import os
import struct
import subprocess
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, HERE)
sys.path.insert(0, TOOLS)

import helpers  # noqa: E402

PATCH_FILE = os.path.join(ROOT, "patches", "aux-boot-restore.json")
AUX_ACTIVATE = 0x02303474  # C_HMI_MEDIA_APP_BASE::HandleAudioAuxInputStatusChnged
AUX_BOOT_ACTIVATE = 0x022C0678  # C_HMI_MEDIA_APP_BASE::InitApp, the AUX source
PRIORITY_LOAD = 0x01699444  # C_MGR_SRC::StartUp


def word(hexstr):
    return struct.unpack(">I", bytes.fromhex(hexstr))[0]


def edits():
    spec = json.loads(Path(PATCH_FILE).read_text())
    return {int(p["addr"], 16): p for p in spec["variants"]["NAV"]["patches"]}


def test_first_edit_makes_auxs_activate_call_pass_pronly_false():
    """`li r4, 1` (ActivateSource's PrOnly argument for AUX) becomes `li r4, 0`."""
    p = edits()[AUX_ACTIVATE]
    for field, want in (("expect", 1), ("bytes", 0)):
        w = word(p[field])
        assert w >> 26 == 14 and (w >> 16) & 0x1F == 0, "li form: addi rD, 0, imm"
        assert (w >> 21) & 0x1F == 4, "r4: the bool argument, after `this` in r3"
        assert w & 0xFFFF == want


def test_initapp_edit_makes_auxs_boot_activation_pass_pronly_false():
    """The boot-time `ActivateSource(aux, true)` in InitApp - the request the restore sees.

    The handler edit alone was flashed and AUX's boot request still arrived with PrOnly set.
    """
    p = edits()[AUX_BOOT_ACTIVATE]
    for field, want in (("expect", 1), ("bytes", 0)):
        w = word(p[field])
        assert w >> 26 == 14 and (w >> 16) & 0x1F == 0, "li form: addi rD, 0, imm"
        assert (w >> 21) & 0x1F == 4, "r4: the bool argument, after `this` in r3"
        assert w & 0xFFFF == want


def test_second_edit_loads_auxs_priority_instead_of_the_saved_one():
    """`lwz r0, 8(r1)` (saved Last_Source_Priority) becomes `li r0, 20`."""
    p = edits()[PRIORITY_LOAD]
    w = word(p["expect"])
    assert (w >> 26, (w >> 21) & 0x1F, (w >> 16) & 0x1F, w & 0xFFFF) == (32, 0, 1, 8)
    w = word(p["bytes"])
    assert w >> 26 == 14 and (w >> 16) & 0x1F == 0, "li form: addi rD, 0, imm"
    assert (w >> 21) & 0x1F == 0, "into r0, which 0x01699448 stores to this+0xac"
    assert w & 0xFFFF == 20, "AUX's priority, from the spy request-list dump"


def test_shipped_definition_applies_and_cascades(tmp_path):
    """End-to-end: patches/aux-boot-restore.json applies through patch_smeg.py."""
    img = bytearray(
        helpers.make_image_with_build("5.43.A.R2", size=0x1304000)
    )  # reaches 0x02303474
    for addr, p in edits().items():
        off = addr - 0x01000000
        img[off : off + 4] = bytes.fromhex(p["expect"])

    src = tmp_path / "SMEG_PLUS_UPG"
    src.mkdir()
    helpers.build_package(str(src), variant="NAV", img=bytes(img))

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
            "NAV",
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr

    bq = out / "NAV" / "AppBin" / "f_BigQuick.bin"
    patched = helpers.inflate_container(bq.read_bytes())
    for addr, p in edits().items():
        off = addr - 0x01000000
        assert patched[off : off + 4].hex() == p["bytes"], "edit at %#x did not land" % addr
