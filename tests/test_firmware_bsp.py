"""Firmware-in-the-loop tests for the BSP kernel image: YOUR OWN stock `vxWorks.bin`, never CI.

`BSP/SMEG_PLUS_512/vxWorks.bin` is not an ELF — a raw PowerPC image — and it is where the kernel
addresses this repository's patches branch to live (`patches/diagnostic-logsink.json` jumps to
`logMsg`). What the docs could previously only call *read* is settled here on the real image, and
these tests skip cleanly wherever it is not provided:

    SMEG_VXWORKS_IMAGE=~/Downloads/SMEG_PLUS_UPG/BSP/SMEG_PLUS_512/vxWorks.bin \\
        .venv/bin/python -m pytest -m firmware -q

Addresses are per build — `SMEG_PLUS_256/vxWorks.bin` is the 512 image displaced — so the two
address checks below are written against the 512 image the docs quote.
"""

import os
import struct
import sys
from pathlib import Path

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

IMAGE_ENV = "SMEG_VXWORKS_IMAGE"

# the two kernel addresses docs/FLASH_CHAIN.md and docs/PATCHES.md name, on this build
TICKGET = 0x0058C248
LOGMSG = 0x00484A94

pytestmark = [
    pytest.mark.firmware,
    pytest.mark.skipif(not os.environ.get(IMAGE_ENV), reason="set %s to run" % IMAGE_ENV),
]


@pytest.fixture(scope="module")
def kernel():
    return Path(os.path.expanduser(os.environ[IMAGE_ENV])).read_bytes()


def test_the_image_is_a_raw_kernel_not_an_elf(kernel):
    """`94 21 ff e0` at offset 0 is `stwu r1,-0x20(r1)` - raw code, no ELF header."""
    assert kernel[:4] == bytes.fromhex("9421ffe0")
    assert kernel[:4] != b"\x7fELF"


def test_the_symbol_table_is_found_at_the_documented_address(kernel):
    """*(executed)* The table is at file `0x622024`, i.e. address `0x00822024` - not mid-image.

    The scan used to return the longest *unbroken* run of resolving entries. The real table has
    unreadable entries in its middle, so that landed thousands of entries in and returned about
    two thirds of the symbols; the corrected scan walks back over those gaps to the first entry.
    """
    import symbols

    offset = symbols.find_vxworks_symtab(kernel)
    assert offset == 0x622024
    assert symbols.VXWORKS_BASE + offset == 0x00822024


def test_the_table_is_read_at_the_documented_base_and_stride(kernel):
    """*(executed)* `0x00200000` resolves the name pointers; the stride is 20 bytes.

    Reading the same table at the *application's* base resolves nothing, which is what makes the
    base a measurement rather than an assumption.
    """
    import symbols

    offset = symbols.find_vxworks_symtab(kernel)
    assert len(symbols.load_vxworks_symtab(kernel)) > 13000
    assert symbols.load_vxworks_symtab(kernel, base=0x01000000) == {}

    first = struct.unpack_from(">5I", kernel, offset)
    second = struct.unpack_from(">5I", kernel, offset + symbols.VXWORKS_ENTRY_SIZE)
    assert first[0] == first[3] == 0 and second[0] == second[3] == 0  # the two `unk` words
    assert first[1] != second[1] and first[2] != second[2]  # distinct name and address
    assert first[4] in symbols.VXWORKS_TYPE_NAMES


def test_the_table_names_the_two_addresses_the_docs_claim(kernel):
    """The key check, now executed: `0x0058c248` is `tickGet` and `logMsg` is `0x00484a94`."""
    import symbols

    syms = symbols.load_vxworks_symtab(kernel)
    assert syms[TICKGET] == "tickGet"
    assert syms[LOGMSG] == "logMsg"


def test_the_type_word_is_bousqi_codes_with_the_zero_hundred_bit(kernel):
    """*(executed)* The four codes are the low bits; the word itself is never a bare code."""
    import symbols

    offset = symbols.find_vxworks_symtab(kernel)
    seen = {typ for _, _, typ in symbols.iter_vxworks_symtab(kernel, offset)}
    assert set(symbols.VXWORKS_TYPE_NAMES) <= seen
    assert seen & {0x100, 0x400, 0x800, 0x1000} == set()


def test_a_code_symbol_is_code_and_a_global_is_data(kernel):
    """The kind bits checked against the bytes, in both directions.

    `tickGet` is 0x400-kind and its address holds an instruction (`lwz r3,-0x5f84(r13)` then
    `blr`); `g_UBootVersion` is 0x800-kind and its address is `.bss`, all zeros in the file.
    """
    import symbols

    offset = symbols.find_vxworks_symtab(kernel)
    kinds = {addr: typ for addr, _, typ in symbols.iter_vxworks_symtab(kernel, offset)}
    assert kinds[TICKGET] == 0x500
    assert kernel[TICKGET - symbols.VXWORKS_BASE :][:8] == bytes.fromhex("806da07c4e800020")
    assert kinds[0x007A14A8] == 0x900
    assert kernel[0x007A14A8 - symbols.VXWORKS_BASE :][:8] == bytes(8)
