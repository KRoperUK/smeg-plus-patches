"""Tests for the shared symbol-map reader, and the VxWorks table in a raw kernel image.

Worth testing properly because the analysis tools that use it are themselves listed as
untested in `AGENTS.md` (issue #38), so this is the closest thing they have to a net. The
parse is small, but it is the shared answer to "what is this address called", and getting that
wrong is silent.

The VxWorks half is tested the same way for a harder reason: the 20-byte entry is a third
party's description of a format this repository cannot check against a vendor image in CI, so
the image and the table are built here and the reader is held to what it was asked to be -
tolerant about entries it cannot read, and silent about nothing else.
"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import symbols  # noqa: E402

BASE = 0x01000000


def test_header_and_blank_lines_are_not_symbols(tmp_path):
    p = tmp_path / "symbols.txt"
    p.write_text(
        "Symbol table for f_BigQuick.bin\n"
        "\n"
        "01000000 T alpha\n"
        "not-a-hex T ignored\n"
        "01000100 T beta\n"
    )
    assert symbols.load_symbols(str(p)) == {BASE: "alpha", BASE + 0x100: "beta"}


def test_the_last_name_at_an_address_wins(tmp_path):
    """The behaviour the four copies had disagreed about.

    Three used `addr = name` and one used `setdefault`, so a duplicated address resolved to the
    last name in three tools and the first in the fourth - two tools reading one map and
    disagreeing about what a symbol is called. Last-wins is what the analysis tools have always
    done, so last-wins is what the shared reader does.
    """
    p = tmp_path / "symbols.txt"
    p.write_text("01000000 T first_name\n01000000 T second_name\n")
    assert symbols.load_symbols(str(p))[BASE] == "second_name"


def test_two_field_lines_are_ignored(tmp_path):
    """Only `<addr> <type> <name>` counts; a bare address/type pair has no name."""
    p = tmp_path / "symbols.txt"
    p.write_text("01000000 T alpha\n01000100 T\n")
    assert symbols.load_symbols(str(p)) == {BASE: "alpha"}


def test_extents_run_to_the_next_symbol(tmp_path):
    p = tmp_path / "symbols.txt"
    p.write_text("01000000 T alpha\n01000100 T beta\n")
    syms = symbols.load_symbols(str(p))
    ext = symbols.extents(syms, 0x400, BASE)
    assert ext["alpha"] == (BASE, 0x100)
    assert ext["beta"] == (BASE + 0x100, 0x400 - 0x100)


def test_the_last_symbol_gets_the_rest_of_the_image():
    """A documented over-statement: maps carry no sizes, so the last symbol absorbs the tail."""
    ext = symbols.extents({BASE: "only"}, 0x1000, BASE)
    assert ext["only"] == (BASE, 0x1000)


def test_name_at_finds_the_containing_symbol():
    ext = symbols.extents({BASE: "alpha", BASE + 0x100: "beta"}, 0x400, BASE)
    assert symbols.name_at(ext, BASE + 0x40) == "alpha"
    assert symbols.name_at(ext, BASE + 0x100) == "beta"


def test_name_at_is_none_below_the_first_symbol():
    ext = symbols.extents({BASE + 0x100: "beta"}, 0x400, BASE)
    assert symbols.name_at(ext, BASE) is None


# --- the VxWorks symbol table in a raw kernel image -------------------------

KERNEL_BASE = symbols.VXWORKS_BASE  # 0x00200000, the base docs/FLASH_CHAIN.md records
TABLE_AT = 0x1000  # file offset of the table in the fixtures below
STRINGS_AT = 0x4000


def build_vxworks_image(entries, size=0x8000, table_at=TABLE_AT, strings_at=STRINGS_AT):
    """A synthetic raw VxWorks image carrying a 20-byte-entry symbol table.

    `entries` is a list of `(name, address, type)`. The name is placed in the image's string
    area and the entry holds its address, which is the only way a name pointer is meant to
    resolve. A `name` that is `None` writes a pointer that resolves nowhere, and an `int` is
    used as the pointer verbatim - between them those two cover every way a reader can be
    handed an entry it must skip.
    """
    image = bytearray(size)
    image[0:4] = bytes.fromhex("9421ffe0")  # stwu r1,-0x20(r1): a raw image, not an ELF
    strings = bytearray()
    table = bytearray()
    for name, address, typ in entries:
        if isinstance(name, int):
            ptr = name
        elif name is None:
            ptr = 0xDEADBEEF  # outside the image, so it resolves to nothing
        else:
            ptr = KERNEL_BASE + strings_at + len(strings)
            strings += name.encode("ascii") + b"\x00"
        table += struct.pack(">5I", 0, ptr, address, 0, typ)
    image[table_at : table_at + len(table)] = table
    image[strings_at : strings_at + len(strings)] = strings
    return bytes(image)


THREE = [
    ("tickGet", KERNEL_BASE + 0x0200, 0x400),
    ("logMsg", KERNEL_BASE + 0x0400, 0x400),
    ("g_UBootVersion", KERNEL_BASE + 0x0600, 0x800),
]


def test_it_reads_the_table_and_names_the_addresses():
    image = build_vxworks_image(THREE)
    assert symbols.load_vxworks_symtab(image, offset=TABLE_AT) == {
        KERNEL_BASE + 0x0200: "tickGet",
        KERNEL_BASE + 0x0400: "logMsg",
        KERNEL_BASE + 0x0600: "g_UBootVersion",
    }


def test_the_table_is_found_without_being_told_where_it_is():
    """The real table has no header pointing at it, so the reader has to locate it."""
    entries = [("sym_%02d" % i, KERNEL_BASE + 0x100 * i, 0x400) for i in range(10)]
    syms = symbols.load_vxworks_symtab(build_vxworks_image(entries))

    assert symbols.find_vxworks_symtab(build_vxworks_image(entries)) == TABLE_AT
    assert syms == {KERNEL_BASE + 0x100 * i: "sym_%02d" % i for i in range(10)}


def test_a_handful_of_resolving_words_is_not_mistaken_for_a_table():
    """The guard that makes the scan a check rather than a guess: `min_run` is real.

    Three entries is a table by construction here and would be a coincidence anywhere else,
    which is exactly the case the default has to refuse. `min_run` is what a caller uses when
    they know better.
    """
    image = build_vxworks_image(THREE)
    assert symbols.find_vxworks_symtab(image) is None
    assert symbols.load_vxworks_symtab(image) == {}
    assert symbols.find_vxworks_symtab(image, min_run=3) == TABLE_AT


def test_entries_whose_name_pointer_does_not_resolve_are_skipped():
    """One unreadable entry must not cost the walk the rest of the table.

    Three ways to fail are exercised: no pointer at all, a pointer at the image's code (not
    printable), and a pointer at a NUL padding byte (nothing to read).
    """
    image = build_vxworks_image(
        [
            ("tickGet", KERNEL_BASE + 0x0200, 0x400),
            (None, KERNEL_BASE + 0x0300, 0x400),
            ("logMsg", KERNEL_BASE + 0x0400, 0x400),
            (KERNEL_BASE, KERNEL_BASE + 0x0500, 0x400),  # file offset 0: not a string
            ("g_UBootVersion", KERNEL_BASE + 0x0600, 0x800),
            (0xDEADBEEF, KERNEL_BASE + 0x0650, 0x400),
            ("sysClkRateSet", KERNEL_BASE + 0x0700, 0x400),
        ]
    )
    assert symbols.load_vxworks_symtab(image, offset=TABLE_AT) == {
        KERNEL_BASE + 0x0200: "tickGet",
        KERNEL_BASE + 0x0400: "logMsg",
        KERNEL_BASE + 0x0600: "g_UBootVersion",
        KERNEL_BASE + 0x0700: "sysClkRateSet",
    }


def test_a_gap_is_stepped_over_but_not_endlessly():
    """A miss is skipped — until `max_gap` of them in a row, which is what the table's end
    looks like. Both halves matter: without the bound a stray offset walks to the end of the
    image, and without the tolerance one unreadable entry ends the table early.
    """
    image = build_vxworks_image([(None, KERNEL_BASE, 0x400)] * 80 + THREE)

    assert symbols.load_vxworks_symtab(image, offset=TABLE_AT) == {}
    assert symbols.load_vxworks_symtab(image, offset=TABLE_AT, max_gap=100) == {
        KERNEL_BASE + 0x0200: "tickGet",
        KERNEL_BASE + 0x0400: "logMsg",
        KERNEL_BASE + 0x0600: "g_UBootVersion",
    }


def test_count_caps_how_many_entries_are_examined():
    image = build_vxworks_image(THREE)
    assert symbols.load_vxworks_symtab(image, offset=TABLE_AT, count=2) == {
        KERNEL_BASE + 0x0200: "tickGet",
        KERNEL_BASE + 0x0400: "logMsg",
    }


def test_the_last_name_at_a_kernel_address_wins():
    """The same rule as the symbol-map reader: the two must not disagree."""
    image = build_vxworks_image(
        [
            ("first_name", KERNEL_BASE + 0x200, 0x400),
            ("second_name", KERNEL_BASE + 0x200, 0x400),
        ]
    )
    assert symbols.load_vxworks_symtab(image, offset=TABLE_AT) == {
        KERNEL_BASE + 0x200: "second_name"
    }


def test_the_type_codes_come_back_from_the_iterator():
    """The four codes are a third party's, so they are reported, never filtered on."""
    image = build_vxworks_image(
        [
            ("unk_one", KERNEL_BASE + 0x200, 0x100),
            ("func_one", KERNEL_BASE + 0x300, 0x400),
            ("data_one", KERNEL_BASE + 0x400, 0x800),
            ("ext_one", KERNEL_BASE + 0x500, 0x1000),
            ("odd_type", KERNEL_BASE + 0x600, 0x2000),  # not in the enum; still a name
        ]
    )
    got = list(symbols.iter_vxworks_symtab(image, TABLE_AT))
    assert got == [
        (KERNEL_BASE + 0x200, "unk_one", 0x100),
        (KERNEL_BASE + 0x300, "func_one", 0x400),
        (KERNEL_BASE + 0x400, "data_one", 0x800),
        (KERNEL_BASE + 0x500, "ext_one", 0x1000),
        (KERNEL_BASE + 0x600, "odd_type", 0x2000),
    ]
    assert [symbols.VXWORKS_TYPE_NAMES[t] for _, _, t in got[:4]] == [
        "unk",
        "func",
        "data",
        "ext",
    ]


def test_the_map_feeds_extents_and_name_at():
    """A kernel address can be named the same way an application one is."""
    image = build_vxworks_image(
        [
            ("alpha", KERNEL_BASE + 0x200, 0x400),
            ("beta", KERNEL_BASE + 0x300, 0x400),
        ]
    )
    syms = symbols.load_vxworks_symtab(image, offset=TABLE_AT)
    ext = symbols.extents(syms, len(image), KERNEL_BASE)

    assert symbols.name_at(ext, KERNEL_BASE + 0x210) == "alpha"
    assert symbols.name_at(ext, KERNEL_BASE + 0x300) == "beta"
    assert symbols.name_at(ext, KERNEL_BASE + 0x100) is None


def test_an_image_with_no_table_returns_an_empty_map():
    """`vxWorks.bin` is not the only raw image; the application image is not one of these."""
    assert symbols.load_vxworks_symtab(bytes(0x4000)) == {}


def test_a_pointer_to_something_that_is_not_printable_is_not_a_name():
    """The same pointer resolves as a name until the string it aims at stops being one.

    This is the test that says the printable check is load-bearing: without it the pointer
    would still be followed and the entry reported with whatever bytes were there.
    """
    entry = [("tickGet", KERNEL_BASE + 0x200, 0x400)]
    assert symbols.load_vxworks_symtab(build_vxworks_image(entry), offset=TABLE_AT) == {
        KERNEL_BASE + 0x200: "tickGet"
    }

    image = bytearray(build_vxworks_image(entry))
    image[STRINGS_AT : STRINGS_AT + 8] = b"\x01\x02\x03\x04\x05tick\x00"
    assert symbols.load_vxworks_symtab(bytes(image), offset=TABLE_AT) == {}
