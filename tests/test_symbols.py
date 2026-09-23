"""Tests for the shared symbol-map reader.

Worth testing properly because the analysis tools that use it are themselves listed as
untested in `AGENTS.md` (issue #38), so this is the closest thing they have to a net. The
parse is small, but it is the shared answer to "what is this address called", and getting that
wrong is silent.
"""

import os
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
