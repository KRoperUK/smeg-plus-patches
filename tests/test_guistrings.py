"""The GUI string table codec, on files this test builds itself.

No vendor firmware is involved: `tools/guistrings.py` writes a table, the test reads it back
and checks the bytes against the layout the loader and the vendor's own writer agree on. The
same codec is then pointed at a real extracted partition by
`tests/test_firmware_gui_strings.py`, which is skipped unless you set `SMEG_MEDIA_DIR`.

All the integers here are big-endian, and a "unit" is one UTF-16 code unit (two bytes).
"""

import json
import os
import struct
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import guistrings  # noqa: E402

GS = guistrings


def build(pairs):
    """A .xml.bin built the way the tool builds one, returned parsed."""
    entries = [GS.Entry(i, 0, 0, text) for i, text in pairs]
    blob = GS.StringsFile(0, len(entries), 0, 0, entries, 0).to_bytes()
    return blob


def parsed(pairs):
    return GS.StringsFile.parse(build(pairs))


# ---------------------------------------------------------------- the layout


def test_the_writer_emits_the_documented_layout():
    """Two short strings, spelled out byte by byte.

    header: total 0x30, count 2, strings base 0x10 + 12*2 = 0x28, reserved 0
    record: id, absolute offset, length in *bytes* (not characters)
    """
    blob = build([(1, "AB"), (2, "CD")])
    assert blob == bytes.fromhex(
        "00000030"  # total file size
        "00000002"  # record count
        "00000028"  # first string's offset
        "00000000"  # reserved, always zero
        "00000001"
        "00000028"
        "00000004"  # id 1 at 0x28, 4 bytes
        "00000002"
        "0000002c"
        "00000004"  # id 2 at 0x2c, 4 bytes
        "00410042"  # AB
        "00430044"  # CD
    )
    assert len(blob) == 0x30


def test_header_fields_describe_the_records():
    f = parsed([(3, "USB"), (4, "CD"), (9, "AUX")])
    assert f.count_field == 3
    assert f.base_field == 0x10 + 12 * 3
    assert f.reserved == 0
    assert f.size_field == f.file_length
    assert [e.id for e in f.entries] == [3, 4, 9]
    assert [e.text for e in f.entries] == ["USB", "CD", "AUX"]
    assert [e.offset for e in f.entries] == [f.base_field, f.base_field + 6, f.base_field + 10]
    assert [e.length for e in f.entries] == [6, 4, 6]
    assert all(ok for _, ok in f.issues())


def test_no_terminator_and_no_padding_between_strings():
    """The next record's offset is the previous record's offset + its length, exactly."""
    f = parsed([(1, "a"), (2, ""), (3, "ccc")])
    assert f.file_length == f.base_field + 2 + 0 + 6
    assert f.entries[1].length == 0
    assert f.entries[2].offset == f.entries[1].offset


def test_a_string_is_utf16be_not_latin1():
    f = parsed([(1, "Džuboks")])
    assert f.entries[0].length == 14
    assert f.to_bytes()[f.base_field :] == "Džuboks".encode("utf-16-be")


def test_an_astral_character_costs_four_bytes():
    f = parsed([(1, "😀")])
    assert f.entries[0].length == 4
    assert f.entries[0].text == "😀"
    assert f.to_bytes() == build([(1, "😀")])


# ---------------------------------------------------------------- round trip


@pytest.mark.parametrize(
    "pairs",
    [
        [],
        [(0, "DY")],
        [(0, "DY"), (1, "DAB Radio"), (2, "AM Radio"), (9, "AUX")],
        [(i, "value %d" % i) for i in range(50)],
        [(10, ""), (11, "multi\r\nline"), (12, "tab\there"), (13, "\\escaped")],
        [(1, "\ud800")],  # a lone surrogate: not real text, but it must survive
    ],
)
def test_decode_then_rebuild_is_byte_identical(pairs):
    blob = build(pairs)
    assert GS.StringsFile.parse(blob).to_bytes() == blob


def test_the_id_space_may_have_holes():
    f = parsed([(0, "a"), (7, "b"), (2652, "c")])
    assert [e.id for e in f.entries] == [0, 7, 2652]
    assert f.count_field == 3
    assert f.to_bytes() == build([(0, "a"), (7, "b"), (2652, "c")])


# ---------------------------------------------------------------- refusing junk


def test_a_file_shorter_than_the_header_is_refused():
    with pytest.raises(GS.GuiStringsError, match="shorter than"):
        GS.StringsFile.parse(b"\x00" * 12)


def test_a_directory_that_runs_past_the_end_is_refused():
    blob = build([(1, "AB")])
    lying = blob[:4] + struct.pack(">I", 9999) + blob[8:]
    with pytest.raises(GS.GuiStringsError, match="past the"):
        GS.StringsFile.parse(lying)


def test_an_odd_length_is_refused():
    """Every shipped string is whole UTF-16 code units; one that is not is not this format."""
    blob = bytearray(build([(1, "AB")]))
    blob[0x18:0x1C] = struct.pack(">I", 3)
    with pytest.raises(GS.GuiStringsError, match="odd length"):
        GS.StringsFile.parse(bytes(blob))


def test_a_record_pointing_past_the_end_is_refused():
    blob = bytearray(build([(1, "AB")]))
    blob[0x14:0x18] = struct.pack(">I", 0x1000)
    with pytest.raises(GS.GuiStringsError, match="past the"):
        GS.StringsFile.parse(bytes(blob))


# ---------------------------------------------------------------- editing


def test_an_exact_edit_moves_every_later_offset():
    f = parsed([(1, "AUX"), (2, "Video")])
    entries, notes = GS.apply_overrides(f.entries, {1: "CarPlay"})
    assert notes == []
    out = f.to_bytes(entries)
    g = GS.StringsFile.parse(out)
    assert g.entries[0].text == "CarPlay"
    assert g.entries[0].length == 14
    # 8 bytes longer, so the next string and the file move by exactly 8
    assert g.entries[1].offset == f.entries[1].offset + 8
    assert len(out) == f.file_length + 8
    assert all(ok for _, ok in g.issues())


def test_pad_keeps_the_file_and_every_offset_exactly_as_they_were():
    f = parsed([(1, "AUX"), (2, "Video")])
    entries, _ = GS.apply_overrides(f.entries, {1: "US"}, pad=True)
    out = f.to_bytes(entries)
    assert len(out) == f.file_length
    g = GS.StringsFile.parse(out)
    assert g.entries[0].length == f.entries[0].length
    assert g.entries[0].text == "US\x00"  # NUL-padded to the slot
    assert g.entries[1].offset == f.entries[1].offset
    # what changed is the slot's own bytes and nothing else
    assert out[: f.base_field] == f.to_bytes()[: f.base_field]


def test_pad_refuses_a_replacement_that_would_not_fit():
    f = parsed([(1, "AUX"), (2, "Video")])
    with pytest.raises(GS.GuiStringsError, match="slot is"):
        GS.apply_overrides(f.entries, {1: "CarPlay"}, pad=True)


def test_pad_with_truncate_clips_to_the_slot():
    f = parsed([(1, "AUX"), (2, "Video")])
    entries, notes = GS.apply_overrides(f.entries, {1: "CarPlay"}, pad=True, truncate=True)
    out = f.to_bytes(entries)
    assert len(out) == f.file_length
    assert GS.StringsFile.parse(out).entries[0].text == "Car"
    assert notes and "clipped" in notes[0]


def test_an_unknown_id_is_refused_unless_asked_for():
    f = parsed([(1, "AUX")])
    with pytest.raises(GS.GuiStringsError, match="no such string id: 99"):
        GS.apply_overrides(f.entries, {99: "x"})
    entries, _ = GS.apply_overrides(f.entries, {99: "x"}, allow_new_id=True)
    g = GS.StringsFile.parse(f.to_bytes(entries))
    assert [e.id for e in g.entries] == [1, 99]
    assert g.entries[1].text == "x"


def test_editing_nothing_rebuilds_nothing():
    f = parsed([(1, "AUX"), (2, "Video")])
    entries, notes = GS.apply_overrides(f.entries, {})
    assert notes == []
    assert f.to_bytes(entries) == build([(1, "AUX"), (2, "Video")])


# ---------------------------------------------------------------- overrides files


def test_overrides_are_read_from_json_with_string_or_int_ids(tmp_path):
    p = tmp_path / "edits.json"
    p.write_text(json.dumps({"9": "CarPlay", "10": "Video"}), encoding="utf-8")
    assert GS.load_overrides(str(p)) == {9: "CarPlay", 10: "Video"}


def test_a_wrapped_overrides_file_is_accepted(tmp_path):
    p = tmp_path / "edits.json"
    p.write_text(json.dumps({"strings": {"9": "CarPlay"}}), encoding="utf-8")
    assert GS.load_overrides(str(p)) == {9: "CarPlay"}


def test_a_non_string_override_is_refused(tmp_path):
    p = tmp_path / "edits.json"
    p.write_text(json.dumps({"9": 42}), encoding="utf-8")
    with pytest.raises(GS.GuiStringsError, match="not a string"):
        GS.load_overrides(str(p))


def test_set_arguments_are_parsed():
    assert GS.load_overrides(None, ["9=CarPlay", "10=Video 2"]) == {9: "CarPlay", 10: "Video 2"}
    with pytest.raises(GS.GuiStringsError, match="id=text"):
        GS.load_overrides(None, ["CarPlay"])


# ---------------------------------------------------------------- the CLI


@pytest.fixture
def media_dir(tmp_path):
    """A gui_texts directory with two languages, as the partition lays them out."""
    d = tmp_path / "gui_texts"
    d.mkdir()
    for lang in ("GB", "FR"):
        (d / ("gui_text_strings_%s.xml.bin" % lang)).write_bytes(
            build([(0, "DY"), (1, "DAB Radio"), (9, "AUX" if lang == "GB" else "AUXo")])
        )
    return d


def test_language_of_reads_the_filename(tmp_path):
    assert GS.language_of("/x/gui_text_strings_GB.xml.bin") == "GB"
    assert GS.language_of("/x/gui_texts.xml") is None


def test_resolve_inputs_accepts_a_directory_and_filters_by_language(media_dir):
    assert [p.name for p in GS.resolve_inputs([str(media_dir)])] == [
        "gui_text_strings_FR.xml.bin",
        "gui_text_strings_GB.xml.bin",
    ]
    assert [GS.language_of(p) for p in GS.resolve_inputs([str(media_dir)], "gb")] == ["GB"]
    with pytest.raises(GS.GuiStringsError, match="for language XX"):
        GS.resolve_inputs([str(media_dir)], "XX")


def test_info_reports_the_header(media_dir, capsys):
    assert GS.main(["info", str(media_dir), "--lang", "GB"]) == 0
    out = capsys.readouterr().out
    assert "language    GB" in out
    assert "count=3" in out
    assert "none of its own" in out


def test_info_json(media_dir, capsys):
    assert GS.main(["info", str(media_dir), "--lang", "GB", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["language"] == "GB"
    assert doc["header"]["count"] == 3
    assert all(doc["checks"].values())


def test_dump_writes_a_table_that_is_also_an_overrides_file(media_dir, tmp_path, capsys):
    assert GS.main(["dump", str(media_dir), "--lang", "GB", "--json"]) == 0
    table = json.loads(capsys.readouterr().out)
    assert table == {"0": "DY", "1": "DAB Radio", "9": "AUX"}
    # the dump is a valid overrides file, and feeding it straight back is a no-op rebuild
    edits = tmp_path / "edits.json"
    edits.write_text(json.dumps(table), encoding="utf-8")
    assert GS.load_overrides(str(edits)) == {0: "DY", 1: "DAB Radio", 9: "AUX"}


def test_dump_text_escapes_control_characters(tmp_path, capsys):
    p = tmp_path / "gui_text_strings_GB.xml.bin"
    p.write_bytes(build([(1, "two\r\nlines")]))
    assert GS.main(["dump", str(p)]) == 0
    assert "\t" in capsys.readouterr().out
    assert GS.main(["dump", str(p), "--raw"]) == 0
    assert "two\r\nlines" in capsys.readouterr().out


def test_dump_can_select_ids(media_dir, capsys):
    assert GS.main(["dump", str(media_dir), "--lang", "GB", "--ids", "9"]) == 0
    out = capsys.readouterr().out
    assert "9\tAUX" in out
    assert "1\tDAB Radio" not in out


def test_probe_proves_the_round_trip_and_exits_zero(media_dir, capsys):
    assert GS.main(["probe", str(media_dir)]) == 0
    out = capsys.readouterr().out
    assert out.count("byte-identical") == 2
    assert "internal checksum" in out


def test_probe_flags_a_file_that_does_not_rebuild_to_itself(tmp_path, capsys):
    p = tmp_path / "gui_text_strings_GB.xml.bin"
    p.write_bytes(build([(1, "AUX")]) + b"junk")  # trailing bytes belong to no string
    assert GS.main(["probe", str(p)]) == 1
    out = capsys.readouterr().out
    assert "DIFFERS" in out
    assert "no string carries a NUL" in out  # the rest of the report still prints


def test_build_without_edits_is_a_byte_for_byte_copy(media_dir, tmp_path):
    src = media_dir / "gui_text_strings_GB.xml.bin"
    out = tmp_path / "rebuilt.bin"
    assert GS.main(["build", "--base", str(src), "--out", str(out)]) == 0
    assert out.read_bytes() == src.read_bytes()


def test_patch_in_place_applies_one_override(media_dir):
    src = media_dir / "gui_text_strings_GB.xml.bin"
    before = src.read_bytes()
    assert GS.main(["patch", str(src), "--in-place", "--set", "9=CarPlay"]) == 0
    f = GS.StringsFile.load(src)
    assert {e.id: e.text for e in f.entries}[9] == "CarPlay"
    assert src.stat().st_size == len(before) + 8


def test_patch_refuses_to_overwrite_without_in_place(media_dir, tmp_path):
    src = media_dir / "gui_text_strings_GB.xml.bin"
    out = tmp_path / "same.bin"
    out.write_bytes(src.read_bytes())
    assert GS.main(["patch", str(src), "--out", str(out), "--set", "9=CarPlay"]) == 0
    assert GS.main(["patch", str(src)]) == 2  # neither --out nor --in-place


def test_patch_writes_a_file_the_parser_and_the_checks_accept(media_dir, tmp_path):
    out = tmp_path / "edited.bin"
    assert (
        GS.main(
            [
                "patch",
                str(media_dir / "gui_text_strings_GB.xml.bin"),
                "--out",
                str(out),
                "--set",
                "9=CarPlay",
            ]
        )
        == 0
    )
    f = GS.StringsFile.load(out)
    assert all(ok for _, ok in f.issues())
    assert f.to_bytes() == out.read_bytes()


def test_diff_reports_what_changed(media_dir, capsys):
    a = media_dir / "gui_text_strings_GB.xml.bin"
    b = media_dir / "gui_text_strings_FR.xml.bin"
    assert GS.main(["diff", str(a), str(b)]) == 0
    out = capsys.readouterr().out
    assert "changed:     1" in out
    assert "id 9: AUX -> AUXo" in out
    assert GS.main(["diff", str(a), str(b), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["changed"] == {"9": {"old": "AUX", "new": "AUXo"}}


def test_a_bad_file_exits_two_with_a_message(tmp_path, capsys):
    p = tmp_path / "gui_text_strings_GB.xml.bin"
    p.write_bytes(b"\x00\x00")
    assert GS.main(["info", str(p)]) == 2
    assert "guistrings:" in capsys.readouterr().err


def test_an_empty_table_is_valid_and_round_trips():
    f = parsed([])
    assert f.count_field == 0
    assert f.base_field == 0x10
    assert f.file_length == 0x10
    assert f.to_bytes() == build([])
