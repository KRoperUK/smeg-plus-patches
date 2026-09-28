"""Firmware-in-the-loop tests: run against YOUR OWN stock NAV 5.43.A.R2 image, never in CI.

No vendor image may be in this repository, so CI can only replay synthetic fragments. These
tests settle the behavioural claims the one-off emulations settled - on the real image - and
skip cleanly everywhere the image is not provided:

    SMEG_NAV_IMAGE=~/Downloads/SMEG_PLUS_UPG/NAV/AppBin/f_BigQuick.bin \\
        .venv/bin/python -m pytest -m firmware -q

`SMEG_NAV_IMAGE` may be the `f_BigQuick.bin` container or an already-inflated image. Each test
says what it stubs; a stub's return value is an assumption, not an observation.
"""

import json
import os
import struct
import sys
from pathlib import Path

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

IMAGE_ENV = "SMEG_NAV_IMAGE"
FIRMWARE = "5.43.A.R2"

pytestmark = [
    pytest.mark.firmware,
    pytest.mark.skipif(not os.environ.get(IMAGE_ENV), reason="set %s to run" % IMAGE_ENV),
]


@pytest.fixture(scope="module")
def image():
    from appimage import inflate

    raw = Path(os.path.expanduser(os.environ[IMAGE_ENV])).read_bytes()
    if len(raw) > 0x801 and raw[0x800] == 0x08:
        raw = inflate(raw)[1]
    return raw


def patch_file(name):
    return os.path.join(ROOT, "patches", name + ".json")


def nav_edits(name):
    return json.loads(Path(patch_file(name)).read_text())["variants"]["NAV"]["patches"]


def emulator(image):
    ppcemu = pytest.importorskip("ppcemu")
    pytest.importorskip("unicorn")
    return ppcemu, ppcemu.Emulator(image)


def reg(uc, n):
    from unicorn import ppc_const

    return uc.reg_read(getattr(ppc_const, "UC_PPC_REG_%s" % n))


# ---------------------------------------------------------------- expect bytes


NAV_SETS = sorted(
    p.stem
    for p in Path(ROOT, "patches").glob("*.json")
    if json.loads(p.read_text()).get("variants", {}).get("NAV", {}).get("firmware") == FIRMWARE
)


@pytest.mark.parametrize("name", NAV_SETS)
def test_every_expect_matches_the_real_image(image, name):
    for e in nav_edits(name):
        off = int(e["addr"], 16) - 0x01000000
        want = bytes.fromhex(e["expect"])
        assert image[off : off + len(want)] == want, "%s %s" % (name, e["addr"])


# ------------------------------------------------- C_MGR_SRC::AddRequest (aux-boot-restore)

ADDREQ, EXEC_ALLOC, FORCE, WDCANCEL, MEMCPY, SETNEXT = (
    0x0169815C,
    0x0169740C,
    0x016977D0,
    0x0058C6E4,
    0x002CB648,
    0x01695590,
)


def add_request(image, pronly, table=None):
    """AddRequest for AUX's request (SrcId 0xe200, type 5, pos 7, prio 20).

    Stubbed: the watchdog cancel, ExecuteAllocation, ForceSchedulerPosition, the node
    allocator (returns a scratch node) and memcpy (performed for real).
    """
    ppcemu, e = emulator(image)
    this, req, node = ppcemu.SCRATCH, ppcemu.SCRATCH + 0x1000, ppcemu.SCRATCH + 0x2000
    e.write(this, b"\0" * 0x400)
    e.write_u32(this + 0xB4, 7)  # Last_Source
    e.write_u32(this + 0xAC, 20)  # Last_Source_Priority, as aux-boot-restore forces it
    e.write_u32(this + 0x84, 0x1234)  # the init timer exists
    for i, (pos, prio) in enumerate(table or []):
        e.write_u32(this + 0x370 + 8 * i, pos)
        e.write_u32(this + 0x374 + 8 * i, prio)
    r = bytearray(0x2C)
    struct.pack_into(">H", r, 0, 3)
    struct.pack_into(">I", r, 4, 0xE200)
    struct.pack_into(">I", r, 8, 20)
    struct.pack_into(">I", r, 0x14, 5)
    struct.pack_into(">I", r, 0x18, 7)
    r[0x28] = pronly
    e.write(req, bytes(r))

    def memcpy(uc):
        d, s, n = reg(uc, 3), reg(uc, 4), reg(uc, 5)
        uc.mem_write(d, bytes(uc.mem_read(s, n)))
        return d

    for addr, how in (
        (MEMCPY, memcpy),
        (SETNEXT, node),
        (WDCANCEL, 0),
        (EXEC_ALLOC, 0),
        (FORCE, 0),
    ):
        e.stub(addr, how)
    e.call(ADDREQ, [this, req])
    assert e.error is None, e.error
    table_out = [struct.unpack(">II", e.read(this + 0x370 + 8 * i, 8)) for i in range(10)]
    return {
        "table": [t for t in table_out if t != (0, 0)],
        "flag": e.read(this + 0x3C0, 1)[0],
        "timer_cancelled": e.reached(WDCANCEL),
        "forced": e.reached(FORCE),
    }


def test_pronly_keeps_aux_out_of_the_boot_restore(image):
    out = add_request(image, pronly=1)
    assert out["table"] == [] and out["flag"] == 0 and not out["timer_cancelled"]


def test_without_pronly_aux_matches_the_restore_and_cancels_the_timer(image):
    out = add_request(image, pronly=0)
    assert out["table"] == [(7, 20)] and out["flag"] == 1 and out["timer_cancelled"]


def test_a_second_aux_request_is_forced_to_the_front(image):
    assert add_request(image, pronly=0, table=[(7, 20)])["forced"]


# ------------------------------------ the AUX handler (aux-signal-switch, aux-sticky)

HANDLER = 0x0230331C
GET_SETTING, GET_SIGNAL = 0x025CB258, 0x025CCBE4
CLIENT_PTR, GET_DEVICE, SET_STATE = 0x022AD2C0, 0x022F3750, 0x022F388C
ACTIVATE, RELEASE = 0x0273A248, 0x02739F30


def handler(image, patches, setting, signal, cached):
    """HandleAudioAuxInputStatusChnged with every callee stubbed.

    The client pointer, both queries (writing the value under test), GetMediaDevice (0, with
    a fake source), SetMediaDeviceState, ActivateSource and ReleaseSource.
    """
    ppcemu, e = emulator(image)
    for name in patches:
        e.apply_patch_file(patch_file(name), "NAV")
    e.stub_all = True
    this, client, src = ppcemu.SCRATCH, ppcemu.SCRATCH + 0x80000, ppcemu.SCRATCH + 0x90000
    e.write(this, b"\0" * 0x100)
    e.write(this + 0x51449, bytes([cached]))
    acts, states = [], []

    def get_setting(uc):
        uc.mem_write(reg(uc, 4), struct.pack(">I", setting))

    def get_signal(uc):
        uc.mem_write(reg(uc, 4), bytes([signal]))

    def get_device(uc):
        uc.mem_write(reg(uc, 5) + 0x10, struct.pack(">I", src))

    for addr, how in (
        (GET_SETTING, get_setting),
        (GET_SIGNAL, get_signal),
        (CLIENT_PTR, client),
        (GET_DEVICE, get_device),
        (ACTIVATE, lambda uc: acts.append(reg(uc, 4))),
        (SET_STATE, lambda uc: states.append(reg(uc, 5))),
    ):
        e.stub(addr, how)
    e.call(HANDLER, [this])
    assert e.error is None, e.error
    return {
        "query": "signal" if e.reached(GET_SIGNAL) else "setting",
        "activate": acts,
        "release": e.reached(RELEASE),
        "cached": e.read(this + 0x51449, 1)[0],
    }


def test_stock_handler_follows_the_setting_and_ignores_the_signal(image):
    assert handler(image, [], setting=1, signal=0, cached=0)["activate"] == [1]
    out = handler(image, [], setting=0, signal=1, cached=0)
    assert out["query"] == "setting" and out["activate"] == []


def test_signal_switch_activates_aux_when_the_signal_appears(image):
    out = handler(image, ["aux-signal-switch"], setting=0, signal=1, cached=0)
    assert out["query"] == "signal" and out["activate"] == [1] and out["cached"] == 1


def test_with_boot_restore_the_activation_passes_pronly_zero(image):
    out = handler(image, ["aux-signal-switch", "aux-boot-restore"], setting=0, signal=1, cached=0)
    assert out["activate"] == [0]


def test_a_setting_change_alone_no_longer_activates(image):
    assert handler(image, ["aux-signal-switch"], setting=1, signal=0, cached=0)["activate"] == []


def test_losing_the_signal_releases_aux_unless_sticky(image):
    assert handler(image, ["aux-signal-switch"], setting=1, signal=0, cached=1)["release"]
    out = handler(image, ["aux-signal-switch", "aux-sticky"], setting=1, signal=0, cached=1)
    assert not out["release"] and out["cached"] == 0


# ------------------------------------------------ the media dispatch window (0xcc)

WINDOW = 0x0230961C, 0x02309650
HANDLER_CASE, SHARED_D7_D9, DEFAULT, ABOVE_D9 = 0x02309FBC, 0x0230A190, 0x0230A664, 0x02309650


def dispatch(image, message_id, patched):
    ppcemu, e = emulator(image)
    from unicorn import UC_HOOK_CODE, ppc_const

    if patched:
        e.apply_patch_file(patch_file("aux-signal-switch"), "NAV")
    e.write_u32(ppcemu.SCRATCH + 0x220, message_id)
    out = []

    def leave(uc, addr, _size, _ctx):
        if not WINDOW[0] <= addr < WINDOW[1]:
            out.append(addr)
            uc.emu_stop()

    e.uc.hook_add(UC_HOOK_CODE, leave)
    e.uc.reg_write(ppc_const.UC_PPC_REG_31, ppcemu.SCRATCH)
    e.uc.emu_start(WINDOW[0], 0, count=40)
    return out[0]


def test_the_media_app_drops_the_signal_event_on_stock(image):
    assert dispatch(image, 0xCC, patched=False) == DEFAULT
    assert dispatch(image, 0xCB, patched=False) == HANDLER_CASE


@pytest.mark.parametrize("mid", [0xCB, 0xCA, 0xD7, 0xD8, 0xD9, 0xDA, 0x385, 0x10])
def test_signal_switch_routes_only_0xcc_differently(image, mid):
    assert dispatch(image, mid, patched=True) == dispatch(image, mid, patched=False)
    assert dispatch(image, 0xCC, patched=True) == HANDLER_CASE


# -------------------- C_MGR_SRC::ChangeToNextSchedulerPosition (#188, docs/SCHEDULER.md)

NEXT_POS = 0x01697A70
LOCK, UNLOCK = 0x00583FE0, 0x00584134


def change_to_next(image, nodes, current, clear=False, by_type=False, cur_type=2):
    """ChangeToNextSchedulerPosition over a list of (Sched_Pos, Sched_Typ) request nodes.

    Stubbed: the lock and unlock, and ExecuteAllocation. The nodes are scratch memory holding
    only +0x18, +0x1c and the +0x3c link.
    """
    ppcemu, e = emulator(image)
    this, nodes_at = ppcemu.SCRATCH, ppcemu.SCRATCH + 0x1000
    e.write(this, b"\0" * 0x400)
    e.write_u32(this + 0x80, 0x1234)
    e.write_u32(this + 0xB4, current)
    e.write_u32(this + 0xB0, cur_type)
    for i, (pos, typ) in enumerate(nodes):
        n = nodes_at + 0x40 * i
        e.write_u32(n + 0x18, pos)
        e.write_u32(n + 0x1C, typ)
        e.write_u32(n + 0x3C, n + 0x40 if i + 1 < len(nodes) else 0)
    e.write_u32(this + 0xD4, nodes_at if nodes else 0)
    for addr in (EXEC_ALLOC, LOCK, UNLOCK):
        e.stub(addr, 0)
    r3 = e.call(NEXT_POS, [this, int(clear), int(by_type)])
    assert e.error is None, e.error
    return r3, e.read_u32(this + 0xB4), e.read_u32(this + 0xE4)


def test_next_position_is_always_one_whatever_is_queued(image):
    """The boot-timer case: current 7, requests at 9, 10, 8, 4, 1 -> stores 1, previous 7."""
    assert change_to_next(image, [(9, 0), (10, 0), (8, 0), (4, 0), (1, 1)], 7)[1:] == (1, 7)


def test_next_position_with_nothing_schedulable_changes_nothing(image):
    r3, pos, _ = change_to_next(image, [(0xFF, 2)], 7)
    assert (r3 & 0xFFFFFFFF, pos) == (0xFFFFFFFF, 7)
