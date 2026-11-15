import os
import struct
import subprocess
import sys

import pytest

import helpers

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = os.path.join(ROOT, "tools")


def run(tool, *args):
    return subprocess.run(
        [sys.executable, os.path.join(TOOLS, tool), *map(str, args)],
        capture_output=True,
        text=True,
    )


@pytest.fixture()
def fixture(tmp_path):
    return helpers.make_ppc_analysis_fixture(tmp_path)


def test_ppcdis_resolves_direct_and_indirect_calls(fixture):
    pytest.importorskip("capstone")
    image, symbols = fixture
    result = run("ppcdis.py", image, symbols, "0x01000000", "0x01000018")
    assert result.returncode == 0, result.stderr
    assert "0100000c: bctrl" in result.stdout
    assert "; call target_function" in result.stdout
    assert "01000010: bl" in result.stdout
    assert "; -> target_function" in result.stdout


def test_callers_finds_a_direct_bl_but_not_bctrl(fixture):
    image, symbols = fixture
    result = run("callers.py", image, symbols, "0x01000040")
    assert result.returncode == 0, result.stderr
    assert "callers of 0x1000040 (target_function): 1" in result.stdout
    assert "0x1000010  caller+0x10" in result.stdout


def test_xref_finds_pointer_and_materialised_string_address(fixture):
    image, symbols = fixture
    result = run("xref.py", image, symbols, "Auxiliary_Input")
    assert result.returncode == 0, result.stderr
    assert "string 'Auxiliary_Input' at 0x1000080" in result.stdout
    assert "pointer   @ 0x100001c  in caller+0x1c" in result.stdout
    assert "immediate @ 0x1000024  in caller+0x24" in result.stdout
    assert "total: 1 pointer(s), 1 immediate site(s)" in result.stdout


def _words_image(tmp_path, words, base=0x01000000):
    """A tiny image with hand-encoded words at 0x00.. plus the target string."""
    import struct as _struct

    img = bytearray(0x100)
    for off, word in words.items():
        img[off : off + 4] = _struct.pack(">I", word)
    img[0x80 : 0x80 + len(b"Auxiliary_Input\x00")] = b"Auxiliary_Input\x00"
    image = tmp_path / "words.bin"
    image.write_bytes(bytes(img))
    symbols = tmp_path / "symbols.txt"
    symbols.write_text(
        "%08x T caller\n%08x T target_function\n%08x R aux_name\n"
        % (base, base + 0x40, base + 0x80)
    )
    return str(image), str(symbols)


def test_xref_finds_an_ori_with_a_different_source_register(tmp_path):
    """#251: `ori r4,r3` reads r3 (bits 21-25), not r4 — xref missed it."""
    image, symbols = _words_image(
        tmp_path,
        {
            0x00: 0x3C600100,  # lis r3,0x100
            0x04: 0x60640080,  # ori r4,r3,0x80
        },
    )
    result = run("xref.py", image, symbols, "Auxiliary_Input")
    assert result.returncode == 0, result.stderr
    assert "immediate @ 0x1000004" in result.stdout
    assert "total: 0 pointer(s), 1 immediate site(s)" in result.stdout


def test_xref_does_not_read_the_ori_destination_as_its_source(tmp_path):
    """#251: `ori r5,r6` with a `lis r5` nearby is not a materialisation."""
    image, symbols = _words_image(
        tmp_path,
        {
            0x00: 0x3CA00100,  # lis r5,0x100
            0x04: 0x60C50080,  # ori r5,r6,0x80: reads r6, so no lis applies
        },
    )
    result = run("xref.py", image, symbols, "Auxiliary_Input")
    assert result.returncode == 0, result.stderr
    assert "total: 0 pointer(s), 0 immediate site(s)" in result.stdout


def test_ppcdis_drops_a_register_after_it_is_overwritten(tmp_path):
    """#251: `lwz r3` after `lis/addi r3` leaves no address to annotate."""
    pytest.importorskip("capstone")
    image, symbols = _words_image(
        tmp_path,
        {
            0x00: 0x3C600100,  # lis r3,0x100
            0x04: 0x38630080,  # addi r3,r3,0x80
            0x08: 0x80630000,  # lwz r3,0(r3): r3 is overwritten with unknown data
            0x0C: 0x7C6903A6,  # mtctr r3
            0x10: 0x4E800421,  # bctrl
        },
    )
    result = run("ppcdis.py", image, symbols, "0x01000000", "0x01000014")
    assert result.returncode == 0, result.stderr
    assert "; call " not in result.stdout


def test_mkelf_wraps_the_image_and_symbols_as_powerpc_elf(fixture, tmp_path):
    image, symbols = fixture
    output = tmp_path / "analysis.elf"
    result = run("mkelf.py", image, symbols, output)
    assert result.returncode == 0, result.stderr
    assert "3 symbols" in result.stdout

    elf = output.read_bytes()
    assert elf[:16] == b"\x7fELF\x01\x02\x01\x00" + bytes(8)
    header = struct.unpack(">HHIIIIIHHHHHH", elf[16:52])
    assert header[:4] == (2, 20, 1, 0x01000000)
    section_offset, section_size, section_count = header[5], header[10], header[11]
    assert (section_size, section_count) == (40, 5)

    text = struct.unpack(">IIIIIIIIII", elf[section_offset + 40 : section_offset + 80])
    assert text[1:4] == (1, 0x6, 0x01000000)
    assert elf[text[4] : text[4] + text[5]] == image.read_bytes()

    assert b"caller\x00" in elf
    assert b"target_function\x00" in elf
    assert b"aux_name\x00" in elf


def test_xref_reports_every_copy_of_a_doubled_string(tmp_path):
    """Literals stored twice got references for the first copy only (#256)."""
    img = bytearray(0x100)
    img[0x80 : 0x80 + len(b"Auxiliary_Input\x00")] = b"Auxiliary_Input\x00"
    img[0x90 : 0x90 + len(b"Auxiliary_Input\x00")] = b"Auxiliary_Input\x00"
    img[0x10:0x14] = struct.pack(">I", 0x01000090)  # pointer to the second copy
    image = tmp_path / "words.bin"
    image.write_bytes(bytes(img))
    symbols = tmp_path / "symbols.txt"
    symbols.write_text(
        "%08x T caller\n%08x R aux_name\n%08x R aux_name_copy\n"
        % (0x01000000, 0x01000080, 0x01000090)
    )
    result = run("xref.py", str(image), str(symbols), "Auxiliary_Input")
    assert result.returncode == 0, result.stderr
    assert "string 'Auxiliary_Input' at 0x1000080" in result.stdout
    assert "string 'Auxiliary_Input' at 0x1000090" in result.stdout
    assert "total: 1 pointer(s)" in result.stdout


def test_xref_ignores_unaligned_byte_matches(tmp_path):
    """Only 4-aligned matches are pointers; the rest is string data (#256)."""
    img = bytearray(0x100)
    img[0x11:0x15] = struct.pack(">I", 0x01000080)  # unaligned: not a pointer
    img[0x20:0x24] = struct.pack(">I", 0x01000080)  # aligned: a pointer
    img[0x80 : 0x80 + len(b"Auxiliary_Input\x00")] = b"Auxiliary_Input\x00"
    image = tmp_path / "unaligned.bin"
    image.write_bytes(bytes(img))
    symbols = tmp_path / "symbols.txt"
    symbols.write_text("%08x T caller\n%08x R aux_name\n" % (0x01000000, 0x01000080))
    result = run("xref.py", str(image), str(symbols), "0x01000080")
    assert result.returncode == 0, result.stderr
    assert "total: 1 pointer(s), 0 immediate site(s)" in result.stdout


def test_xref_stops_the_lis_search_at_a_clobber(tmp_path):
    """Any matching `lis` within 29 instructions combined, even past an overwrite (#256)."""
    image, symbols = _words_image(
        tmp_path,
        {
            0x00: 0x3C600100,  # lis r3,0x100
            0x04: 0x80600000,  # lwz r3,0(r0): overwrites r3
            0x08: 0x38630080,  # addi r3,r3,0x80
        },
    )
    result = run("xref.py", image, symbols, "Auxiliary_Input")
    assert result.returncode == 0, result.stderr
    assert "total: 0 pointer(s), 0 immediate site(s)" in result.stdout


def test_ppcdis_validates_the_address_range(fixture, tmp_path):
    """A start below base used to wrap via negative indexing and disassemble the
    wrong bytes with exit 0 (#256)."""
    pytest.importorskip("capstone")
    image, symbols = fixture
    result = run("ppcdis.py", image, symbols, "0x00fffffc", "0x01000010")
    assert result.returncode != 0
    assert "outside the image" in (result.stdout + result.stderr)


def test_mkelf_reads_a_gzipped_symbol_map(fixture, tmp_path):
    """mkelf re-parsed maps with a plain open(); a `.gz` map yielded a 0-symbol ELF (#256)."""
    import gzip as _gzip

    image, symbols = fixture
    gzipped = tmp_path / "symbols.txt.gz"
    gzipped.write_bytes(_gzip.compress(symbols.read_bytes()))
    output = tmp_path / "analysis-gz.elf"
    result = run("mkelf.py", image, str(gzipped), str(output))
    assert result.returncode == 0, result.stderr
    assert "3 symbols" in result.stdout
