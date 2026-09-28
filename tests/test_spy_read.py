"""`spy_read.py` against a synthetic capture laid out as `SPYTAKE` writes one.

The buffer text below is invented in the format the real buffers use (a `<ms>::` trace, the
ScheduledInit lines, the RequestQueueData table), so no real capture - which carries a VIN -
is ever needed. The boot scenario is the 2026-09-28 one: AUX requested with PrOnly true, and
the tuner acknowledged 7.5 s after Last_Source was read.
"""

import io
import os
import subprocess
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
sys.path.insert(0, TOOLS)

import spy_read  # noqa: E402

FAKE_VIN = "ABCDEFGH12345678Z"  # invented; 17 characters of the VIN alphabet

MGR_SRC = """---------------------------------------------------------
                      MGR_SRC SPY
---------------------------------------------------------
1000::Last_Source   : 7 (0x7)
2000::AllocateSource  : MsgSrc = 3, SrcId= 0xe200,Type=5, Sched_Pos= 7, Sched_Typ = 0, PostPone = 1, Suspend = 1
2000::SendWAIT [MsgSrc + Source_ID]  : 3, 0xe200
2100::AllocateSource  : MsgSrc = 10, SrcId= 0xbc00,Type=5, Sched_Pos= 1, Sched_Typ = 1, PostPone = 1, Suspend = 0
8500::SendACK [MsgSrc + Source_ID]  : 10, 0xbc00
9000::ActivateSourceID::p_source_ID   : 57856 (0xe200)

m_Mgr_src_ScheduledInit[0] ->  10 |   1 |POS_TUNER
m_Mgr_src_ScheduledInit[1] ->   0 |   0 |POS_NULL

*****m_Mgr_src_RequestQueueData*****
Nb|src|id|Status|Norm|NoSr|Lock|Type|sche|Post|Susp|PrOnly|
 0|0x3   |0xe200   |WAITING|  20| 255| 255|   5|   7|   0|   1|   1|  true|
 1|0xa   |0xbc00   |ACKNOWL|  10| 254| 254|   5|   1|   1|   1|   0|  false|
 2| | |EMPTY|   0|   0|   0|   0|   0|   2|   0|   0|  false|
"""
MEDIA = "2200\tSystem    : AUDIO_SOURCE_SWITCH, 57856, [0]\n2300\tdBUS      : MEDIA_TRACK_FOUND, [3], [1], [0]\n"
AUDIO = "----------  HiFi module   AUDIO  snapshot : ----\n  - aux_status = 3\n  - bass = 1\n"
PRIVATE = (
    "100\tVIN FromUP 41 42 43 44 45 46 47 48\n"
    "200\tvehicle id %s\n"
    "300\tl_bdAddr <0:3:19:77:cc:eb>\n" % FAKE_VIN
)


def make_capture(root):
    """SPY/<stamp>/TAR/<stamp>-USER.tar.gz holding four buffers."""
    spy = root / "SPY" / "01_202601010000"
    (spy / "TAR").mkdir(parents=True)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for bid, text in (
            ("25300", MGR_SRC),
            ("06301", MEDIA),
            ("15400", AUDIO),
            ("26300", PRIVATE),
        ):
            data = text.encode()
            ti = tarfile.TarInfo("/RAMDISK_SPY/%s/01_202601010000.bin" % bid)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
    (spy / "TAR" / "01_202601010000-USER.tar.gz").write_bytes(buf.getvalue())
    return spy


def run(*args):
    return subprocess.run(
        [sys.executable, os.path.join(TOOLS, "spy_read.py"), *map(str, args)],
        capture_output=True,
        text=True,
    )


def test_boot_report_finds_the_pronly_aux_request_and_the_timer_fallback(tmp_path):
    r = run(make_capture(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "saved Last_Source = 7" in r.stdout
    assert "SrcId 0xe200" in r.stdout and "PrOnly true" in r.stdout and "<- AUX" in r.stdout
    assert "PrOnly true keeps AUX out of the boot restore" in r.stdout
    assert "tuner was acknowledged first, at 8500 ms = Last_Source + 7500 ms" in r.stdout
    assert "ActivateSourceID SrcId 0xe200" in r.stdout
    assert "POS_TUNER (pos 1, prio 10)" in r.stdout


def test_aux_mode_collects_lines_from_all_three_buffers(tmp_path):
    r = run(make_capture(tmp_path), "--aux")
    assert r.returncode == 0, r.stderr
    assert "0xe200" in r.stdout and "57856" in r.stdout and "aux_status = 3" in r.stdout
    assert "bass" not in r.stdout


def test_list_names_the_known_buffers(tmp_path):
    r = run(make_capture(tmp_path), "--list")
    assert r.returncode == 0, r.stderr
    assert "C_MGR_SRC, the source manager" in r.stdout
    assert len(r.stdout.splitlines()) == 4


def test_personal_data_is_redacted_unless_asked(tmp_path):
    spy = make_capture(tmp_path)
    shown = run(spy, "--show", "26300").stdout
    assert FAKE_VIN not in shown and "41 42 43 44" not in shown and "cc:eb" not in shown
    assert "<VIN>" in shown and "<VIN-BYTES>" in shown and "<ADDR>" in shown
    raw = run(spy, "--show", "26300", "--no-redact").stdout
    assert FAKE_VIN in raw


def test_an_extracted_tree_and_the_tar_itself_both_work(tmp_path):
    spy = make_capture(tmp_path)
    tar = next((spy / "TAR").iterdir())
    assert run(tar, "--list").returncode == 0
    with tarfile.open(tar) as tf:
        tf.extractall(tmp_path / "x", filter="data")
    assert "C_MGR_SRC" in run(tmp_path / "x", "--list").stdout


def test_a_folder_without_a_user_archive_explains_what_is_missing(tmp_path):
    (tmp_path / "SPY" / "s").mkdir(parents=True)
    r = run(tmp_path / "SPY" / "s")
    assert r.returncode != 0 and "SPYTAKE" in r.stderr and "traces.bin" in r.stderr


def test_the_queue_parser_reads_pronly_from_the_last_column():
    mgr = spy_read.parse_mgr_src(MGR_SRC)
    assert {q["id"]: q["pronly"] for q in mgr["queue"]} == {0xE200: True, 0xBC00: False}
