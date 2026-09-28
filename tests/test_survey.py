"""`survey.py` inventories every function; these pin what it counts as a reference.

The tool exists because `callers.py` sees only `bl`, and this firmware makes most of its calls
by materialising an address and branching through `ctr`. A survey that silently missed either
kind, or counted a pointer inside code as a vtable entry, would mislabel live code as dead.
"""

import os
import struct
import subprocess
import sys

import helpers

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)

import survey  # noqa: E402
from symbols import load_typed_symbols  # noqa: E402

BASE = 0x01000000


def fixture_with_vtable(tmp_path):
    """The shared analysis fixture plus a data table holding a pointer to target_function."""
    image, symbols = helpers.make_ppc_analysis_fixture(tmp_path)
    img = bytearray(image.read_bytes()) + bytearray(0x40)
    img[0x100:0x104] = struct.pack(">I", BASE + 0x40)
    image.write_bytes(bytes(img))
    with open(symbols, "a") as fh:
        fh.write("%08x D _ZTV5Table\n" % (BASE + 0x100))
    return image, symbols


def rows_by_name(tmp_path):
    image, symbols = fixture_with_vtable(tmp_path)
    rows, fams = survey.survey(image.read_bytes(), load_typed_symbols(str(symbols)), BASE)
    return {r["mangled"]: r for r in rows}, fams


def test_direct_materialised_and_data_references_are_counted_separately(tmp_path):
    rows, _ = rows_by_name(tmp_path)
    t = rows["target_function"]
    assert (t["callers"], t["materialised"], t["pointers"]) == (1, 1, 1)


def test_a_pointer_inside_code_is_not_counted_as_a_table_entry(tmp_path):
    """The fixture's caller holds literal pointers in its own extent; those are not data."""
    image, symbols = helpers.make_ppc_analysis_fixture(tmp_path)
    rows, _ = survey.survey(image.read_bytes(), load_typed_symbols(str(symbols)), BASE)
    t = {r["mangled"]: r for r in rows}["target_function"]
    assert t["pointers"] == 0


def test_materialised_string_is_attached_to_the_function_that_builds_it(tmp_path):
    rows, _ = rows_by_name(tmp_path)
    assert rows["caller"]["strings"] == ["Auxiliary_Input"]
    assert rows["target_function"]["strings"] == []


def test_data_symbols_are_not_functions(tmp_path):
    rows, _ = rows_by_name(tmp_path)
    assert set(rows) == {"caller", "target_function"}


def test_families_group_by_class_prefix_and_name_libraries():
    assert survey.family("C_MGR_SRC::StartUp()") == "C_MGR_SRC"
    assert survey.family("non-virtual thunk to C_NAV_SERVER::Run()") == "C_NAV_SERVER"
    assert survey.family("com_MM_Upgrade_proxy::Call()") == "com_MM"
    assert survey.family("QWidget::show()") == "Qt"
    assert survey.family("sqlite3_open") == "sqlite"
    assert survey.family("doSomething()") == "(free functions)"


def test_cli_writes_the_three_tables_and_lists_unreached_code(tmp_path):
    image, symbols = fixture_with_vtable(tmp_path)
    out = tmp_path / "survey"
    r = subprocess.run(
        [sys.executable, os.path.join(TOOLS, "survey.py"), image, symbols, "--out", out],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "2 functions" in r.stdout
    assert {p.name for p in out.iterdir()} == {"functions.tsv", "families.tsv", "unreached.tsv"}
    unreached = (out / "unreached.tsv").read_text().splitlines()[1:]
    assert [line.split("\t")[3] for line in unreached] == ["caller"]


def test_cli_reads_the_bigquick_container_too(tmp_path):
    image, symbols = fixture_with_vtable(tmp_path)
    raw = image.read_bytes()
    padded = raw + bytes(0x100000)  # inflate() only accepts an image over 1 MB
    container = tmp_path / "f_BigQuick.bin"
    container.write_bytes(helpers.pack_bigquick(padded))
    assert survey.load_image(container) == padded


def test_a_map_that_misses_the_image_is_refused(tmp_path):
    image, _ = helpers.make_ppc_analysis_fixture(tmp_path)
    wrong = tmp_path / "wrong.txt"
    wrong.write_text("00400000 T elsewhere\n")
    r = subprocess.run(
        [sys.executable, os.path.join(TOOLS, "survey.py"), image, wrong, "--out", tmp_path / "o"],
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
    assert "no code symbols" in r.stderr
