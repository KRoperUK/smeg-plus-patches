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
    rows, fams, _ = survey.survey(image.read_bytes(), load_typed_symbols(str(symbols)), BASE)
    return {r["mangled"]: r for r in rows}, fams


def test_direct_materialised_and_data_references_are_counted_separately(tmp_path):
    rows, _ = rows_by_name(tmp_path)
    t = rows["target_function"]
    assert (t["callers"], t["materialised"], t["pointers"]) == (1, 1, 1)


def test_a_pointer_inside_code_is_not_counted_as_a_table_entry(tmp_path):
    """The fixture's caller holds literal pointers in its own extent; those are not data."""
    image, symbols = helpers.make_ppc_analysis_fixture(tmp_path)
    rows, _, _ = survey.survey(image.read_bytes(), load_typed_symbols(str(symbols)), BASE)
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


def test_cli_writes_the_tables_and_lists_unreached_code(tmp_path):
    image, symbols = fixture_with_vtable(tmp_path)
    out = tmp_path / "survey"
    r = subprocess.run(
        [sys.executable, os.path.join(TOOLS, "survey.py"), image, symbols, "--out", out],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "2 functions" in r.stdout
    assert {p.name for p in out.iterdir()} == {
        "functions.tsv",
        "families.tsv",
        "unreached.tsv",
        "vtables.tsv",
        "virtual_calls.tsv",
        "globals.tsv",
    }
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


def scan(words, tmp_path):
    """Survey a single function made of `words`, with a target function after it."""
    img = bytearray(0x100)
    for k, w in enumerate(words):
        img[k * 4 : k * 4 + 4] = struct.pack(">I", w)
    img[0x80:0x84] = struct.pack(">I", 0x4E800020)  # blr
    sym = tmp_path / "s.txt"
    sym.write_text("%08x T caller\n%08x T target\n" % (BASE, BASE + 0x80))
    rows, _, _ = survey.survey(bytes(img), load_typed_symbols(str(sym)), BASE)
    return {r["mangled"]: r for r in rows}["target"]["materialised"]


def test_a_lis_is_forgotten_once_its_register_is_overwritten(tmp_path):
    """`lis r3,hi; lwz r3,0(r4); addi r3,r3,lo` builds no address from `hi`."""
    words = [0x3C600100, 0x80640000, 0x38630080]
    assert scan(words, tmp_path) == 0
    assert scan([words[0], words[2]], tmp_path) == 1, "the pair alone is still found"


def test_a_call_clobbers_volatile_registers(tmp_path):
    assert scan([0x3C600100, 0x4E800421, 0x38630080], tmp_path) == 0  # lis; bctrl; addi


def test_ori_reads_its_source_from_the_rs_field(tmp_path):
    """`ori r4,r3,lo` combines the `lis r3`; the destination field names r4."""
    assert scan([0x3C600100, 0x60640080], tmp_path) == 1


# ------------------------------------------- vtables, virtual calls, globals (#194)


def vtable_fixture(tmp_path):
    """caller at BASE: a virtual call through slot 4 in the stock `lwz r9,4(r9)` form, a
    store to a BSS global past the end of the image, and a vtable holding target_function."""
    words = {
        0x00: 0x81230000,  # lwz r9,0(r3)       vtable pointer
        0x04: 0x81290004,  # lwz r9,4(r9)       slot 4, same register
        0x08: 0x7D2903A6,  # mtctr r9
        0x0C: 0x4E800421,  # bctrl
        0x10: 0x3D200101,  # lis r9,0x101
        0x14: 0x90090010,  # stw r0,0x10(r9)    -> 0x01010010, a BSS global
        0x18: 0x4E800020,  # blr
        0x40: 0x4E800020,  # target_function: blr
        0x44: 0x4E800020,  # other_function: blr
    }
    img = bytearray(0x100)
    for off, w in words.items():
        img[off : off + 4] = struct.pack(">I", w)
    img[0x80 + 8 : 0x80 + 16] = struct.pack(">II", BASE + 0x44, BASE + 0x40)  # after the header
    image = tmp_path / "vt.bin"
    image.write_bytes(bytes(img))
    sym = tmp_path / "vt.txt"
    sym.write_text(
        "%08x T caller\n%08x T target_function\n%08x T other_function\n"
        "%08x V _ZTV6Widget\n%08x D pad\n%08x B g_counter\n"
        % (BASE, BASE + 0x40, BASE + 0x44, BASE + 0x80, BASE + 0x90, BASE + 0x10010)
    )
    return image, sym


def test_vtable_slots_are_read_after_the_header(tmp_path):
    image, sym = vtable_fixture(tmp_path)
    rows, _, extras = survey.survey(image.read_bytes(), load_typed_symbols(str(sym)), BASE)
    slots = [(off, name) for _, _, off, _, name in extras["vtables"]]
    assert slots == [(0, "other_function"), (4, "target_function")]
    assert {r["mangled"]: r["vslots"] for r in rows}["target_function"] == 1


def test_a_virtual_call_through_the_same_register_is_found(tmp_path):
    image, sym = vtable_fixture(tmp_path)
    _, _, extras = survey.survey(image.read_bytes(), load_typed_symbols(str(sym)), BASE)
    assert [(site - BASE, off, name) for _, site, off, name in extras["virtual_calls"]] == [
        (0x0C, 4, "caller")
    ]


def test_a_store_to_a_bss_global_past_the_image_is_attributed(tmp_path):
    image, sym = vtable_fixture(tmp_path)
    _, _, extras = survey.survey(image.read_bytes(), load_typed_symbols(str(sym)), BASE)
    assert [(name, rd, wr) for _, name, rd, wr in extras["globals"]] == [
        ("g_counter", [], ["caller"])
    ]


def test_a_gzipped_map_is_read_directly(tmp_path):
    import gzip

    image, sym = vtable_fixture(tmp_path)
    gz = tmp_path / "vt.txt.gz"
    gz.write_bytes(gzip.compress(sym.read_bytes()))
    assert load_typed_symbols(str(gz)) == load_typed_symbols(str(sym))
