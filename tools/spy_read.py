#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

"""Read a SPY capture in one command: the boot timeline, the AUX events, any buffer.

`SPYTAKE` collects every module's trace buffer into `SPY/<stamp>/TAR/<stamp>-USER.tar.gz`,
which `SPYSTORE` copies to the stick. Inside, `RAMDISK_SPY/<id>/<stamp>.bin` holds one module's
buffer, mostly text. Reading one by hand meant untarring and grepping; this reads the tar in
memory and never writes the capture anywhere.

SOURCE may be a `SPY/<stamp>` folder (the newest `TAR/*-USER.tar.gz` is used), a `-USER.tar.gz`
itself, or a folder that already contains `RAMDISK_SPY/`.

  --list        every buffer with its size and first line
  --boot        (default) how the boot source was chosen: C_MGR_SRC's trace, the saved
                Last_Source, each source request with its PrOnly flag, the ScheduledInit
                table, and which source won and when
  --aux         only the AUX-related lines from the source manager, media app and audio module
  --show ID     one buffer, e.g. 25300

**Captures hold personal data.** The settings and Bluetooth buffers carry the VIN, device
addresses and phone numbers. Output is redacted by default (`--no-redact` turns it off, for
your own eyes only). Never commit a capture or paste one into an issue.

usage:
    python3 tools/spy_read.py /Volumes/USB/SPY/01_202609280110
    python3 tools/spy_read.py 01_202609280108-USER.tar.gz --aux
    python3 tools/spy_read.py SPY/01_202609280110 --show 25300
"""

import argparse
import glob
import os
import re
import sys
import tarfile

# buffer ids whose owner is established; anything else is listed by its first line
KNOWN = {
    "25300": "C_MGR_SRC, the source manager (read)",
    "06301": "C_HMI_MEDIA_APP_BASE, the media app (read)",
    "15400": "C_MODULE_AUDIO, the audio module 'HiFi AUDIO snapshot' (read from its header)",
}
AUX_SRC_ID = 0xE200
TUNER_POS = 1
INIT_TIMEOUT_MS = 7500  # C_MGR_SRC's init watchdog, 0x1d4c (docs/SCHEDULER.md)

# VIN: 17 characters of the VIN alphabet with at least one digit and one letter; Bluetooth/MAC
# addresses in both the `aa:bb:..` and the `<0:3:19:..>` forms; phone numbers of 10+ digits
REDACTIONS = [
    (
        re.compile(
            r"\b(?=[A-HJ-NPR-Z0-9]*\d)(?=[A-HJ-NPR-Z0-9]*[A-HJ-NPR-Z])[A-HJ-NPR-Z0-9]{17}\b"
        ),
        "<VIN>",
    ),
    (re.compile(r"\b[0-9a-fA-F]{1,2}(?::[0-9a-fA-F]{1,2}){5}\b"), "<ADDR>"),
    (re.compile(r"\+?\b\d{10,15}\b"), "<NUMBER>"),
]


# a VIN also appears split up: as runs of byte values and as partial tokens, on lines that
# name it (seen in buffer 26300), so on any such line mask both
VIN_LINE = re.compile(r"VIN|[Vv]in_|_vin")
VIN_PARTS = [
    (re.compile(r"\b[0-9A-Fa-f]{2}(?:\s+[0-9A-Fa-f]{2}){3,}\b"), "<VIN-BYTES>"),
    (re.compile(r"(?<=[:=]\s)(?=\w*\d)\w{4,}"), "<VIN-PART>"),
]


def redact(text):
    lines = []
    for line in text.split("\n"):
        if VIN_LINE.search(line):
            for pattern, repl in VIN_PARTS:
                line = pattern.sub(repl, line)
        lines.append(line)
    text = "\n".join(lines)
    for pattern, repl in REDACTIONS:
        text = pattern.sub(repl, text)
    return text


# ------------------------------------------------------------------ loading


def find_tar(source):
    """The `-USER.tar.gz` for a SOURCE argument, or None when SOURCE is an extracted tree."""
    if os.path.isfile(source):
        return source
    if os.path.isdir(os.path.join(source, "RAMDISK_SPY")):
        return None
    tars = sorted(glob.glob(os.path.join(source, "TAR", "*-USER.tar.gz")))
    tars += sorted(glob.glob(os.path.join(source, "*-USER.tar.gz")))
    if not tars:
        raise SystemExit(
            "no *-USER.tar.gz under %s - was SPYTAKE run before SPYSTORE? "
            "(traces.bin is only the crash log)" % source
        )
    return tars[-1]


def load_buffers(source):
    """{buffer id: bytes}. Only the first file of each buffer folder is read."""
    out = {}
    tar = find_tar(source)
    if tar is None:
        base = os.path.join(source, "RAMDISK_SPY")
        for name in sorted(os.listdir(base)):
            folder = os.path.join(base, name)
            if os.path.isdir(folder):
                files = sorted(os.listdir(folder))
                if files:
                    with open(os.path.join(folder, files[0]), "rb") as fh:
                        out[name] = fh.read()
        return out
    with tarfile.open(tar, "r:gz") as tf:
        for m in tf.getmembers():
            parts = m.name.strip("/").split("/")
            if m.isfile() and len(parts) >= 3 and parts[-3] == "RAMDISK_SPY":
                out.setdefault(parts[-2], tf.extractfile(m).read())
    return out


def as_text(blob):
    return blob.replace(b"\0", b"").decode("latin-1")


def is_text(blob):
    head = blob[:512].replace(b"\0", b"")
    printable = sum(32 <= b < 127 or b in (9, 10, 13) for b in head)
    return not head or printable / len(head) > 0.9


def first_line(text):
    for line in text.splitlines():
        line = line.strip()
        if line and not set(line) <= set("-=* "):
            return line
    return ""


# ------------------------------------------------------------ C_MGR_SRC buffer

TRACE_RE = re.compile(r"^(\d+)::(.*)$")
FIELD_RE = re.compile(r"(\w+)\s*=\s*(0x[0-9a-fA-F]+|\d+)")
PAIR_RE = re.compile(r":\s*(\d+),\s*(0x[0-9a-fA-F]+)\s*$")
PAREN_ID_RE = re.compile(r"\((0x[0-9a-fA-F]+)\)\s*$")
INIT_RE = re.compile(r"ScheduledInit\[(\d+)\]\s*->\s*(\d+)\s*\|\s*(\d+)\s*\|(\S+)")


def num(s):
    return int(s, 16) if s.lower().startswith("0x") else int(s)


def parse_mgr_src(text):
    """The trace, the ScheduledInit table and the request queue of buffer 25300."""
    trace, init, queue = [], [], []
    in_queue_data = False
    for line in text.splitlines():
        m = TRACE_RE.match(line.strip())
        if m:
            ms, body = int(m.group(1)), m.group(2).strip()
            event = body.split(":")[0].split("[")[0].strip()
            fields = {k: num(v) for k, v in FIELD_RE.findall(body)}
            pair = PAIR_RE.search(body)
            if pair:
                fields.setdefault("MsgSrc", int(pair.group(1)))
                fields.setdefault("SrcId", num(pair.group(2)))
            paren = PAREN_ID_RE.search(body)
            if paren:
                fields.setdefault("SrcId", num(paren.group(1)))
            trace.append({"ms": ms, "event": event, "fields": fields, "text": body})
            continue
        m = INIT_RE.search(line)
        if m:
            init.append({"prio": int(m.group(2)), "pos": int(m.group(3)), "name": m.group(4)})
            continue
        if "RequestQueueData" in line:
            in_queue_data = True
            continue
        if in_queue_data:
            cells = [c.strip() for c in line.split("|")]
            if len(cells) >= 12 and cells[0].isdigit() and cells[2]:
                queue.append(
                    {
                        "src": num(cells[1]),
                        "id": num(cells[2]),
                        "status": cells[3],
                        "prio": int(cells[4]),
                        "type": int(cells[7]),
                        "sched": int(cells[8]),
                        "pronly": cells[-2].lower() == "true"
                        if cells[-1] == ""
                        else cells[-1].lower() == "true",
                    }
                )
            elif line.strip() and not cells[0].isdigit() and not line.startswith("Nb"):
                in_queue_data = False
    return {"trace": trace, "init": init, "queue": queue}


def boot_report(mgr):
    """Lines describing how the boot source was chosen, each tagged with its basis."""
    trace = mgr["trace"]
    lines = []
    last = next((t for t in trace if t["event"].startswith("Last_Source")), None)
    last_val = None
    if last:
        m = re.search(r":\s*(\d+)", last["text"])
        last_val = int(m.group(1)) if m else None
        lines.append("%6d ms  saved Last_Source = %s" % (last["ms"], last_val))
    else:
        lines.append("   -      no Last_Source line (the trace may have wrapped)")

    queue = {q["id"]: q for q in mgr["queue"]}
    for t in trace:
        f = t["fields"]
        if t["event"] == "AllocateSource":
            q = queue.get(f.get("SrcId"))
            pronly = "-" if q is None else ("true" if q["pronly"] else "false")
            lines.append(
                "%6d ms  request  SrcId %-8s pos %-3s type %s  PrOnly %s%s"
                % (
                    t["ms"],
                    hex(f.get("SrcId", 0)),
                    f.get("Sched_Pos", "?"),
                    f.get("Type", "?"),
                    pronly,
                    "   <- AUX" if f.get("SrcId") == AUX_SRC_ID else "",
                )
            )
        elif t["event"] in ("SendACK", "SendSUSPEND", "ReleaseSource", "ActivateSourceID"):
            sid = f.get("SrcId")
            lines.append("%6d ms  %-8s SrcId %s" % (t["ms"], t["event"], hex(sid) if sid else "?"))

    lines.append("  (PrOnly '-': the request was no longer queued when the capture was taken)")
    if mgr["init"]:
        live = [i for i in mgr["init"] if i["pos"]]
        lines.append("")
        lines.append(
            "ScheduledInit: %s"
            % (
                ", ".join("%s (pos %d, prio %d)" % (i["name"], i["pos"], i["prio"]) for i in live)
                or "empty"
            )
        )

    aux = queue.get(AUX_SRC_ID)
    if aux:
        lines.append(
            "AUX request in the queue: PrOnly %s, priority %d, status %s"
            % ("true" if aux["pronly"] else "false", aux["prio"], aux["status"])
        )
        if aux["pronly"]:
            lines.append(
                "  -> PrOnly true keeps AUX out of the boot restore (docs/AUX_CHAIN.md) (read)"
            )

    # which permanent source won first, and whether it looks like the 7.5 s fallback
    tuner_ids = {
        t["fields"].get("SrcId")
        for t in trace
        if t["event"] == "AllocateSource" and t["fields"].get("Sched_Pos") == TUNER_POS
    }
    first_ack = next(
        (
            t
            for t in trace
            if t["event"] == "SendACK" and t["fields"].get("SrcId") in (tuner_ids | {AUX_SRC_ID})
        ),
        None,
    )
    lines.append("")
    if first_ack is None:
        lines.append("verdict: no tuner or AUX acknowledgement in the trace")
    elif first_ack["fields"].get("SrcId") == AUX_SRC_ID:
        lines.append("verdict: AUX was acknowledged first, at %d ms" % first_ack["ms"])
    else:
        msg = "verdict: the tuner was acknowledged first, at %d ms" % first_ack["ms"]
        if last and abs(first_ack["ms"] - last["ms"] - INIT_TIMEOUT_MS) <= 250:
            msg += (
                " = Last_Source + %d ms: the 7.5 s init timer's fallback to the tuner "
                "(inferred from the timing)" % (first_ack["ms"] - last["ms"])
            )
        lines.append(msg)
    return lines


AUX_RE = re.compile(
    r"aux|0xe200|57856|AUDIO_AUX|StatusChng|SIGNAL_STATUS|INPUT_STATUS|0xc[bc]\b", re.IGNORECASE
)


def aux_lines(buffers):
    out = []
    for bid in ("25300", "06301", "15400"):
        if bid not in buffers:
            continue
        hits = [ln.rstrip() for ln in as_text(buffers[bid]).splitlines() if AUX_RE.search(ln)]
        out.append("== %s  %s  (%d line(s))" % (bid, KNOWN.get(bid, ""), len(hits)))
        out += ["  " + h for h in hits]
    return out


# --------------------------------------------------------------------- main


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("source", help="SPY/<stamp> folder, a -USER.tar.gz, or an extracted tree")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true", help="every buffer and its first line")
    mode.add_argument("--boot", action="store_true", help="how the boot source was chosen")
    mode.add_argument("--aux", action="store_true", help="AUX-related lines only")
    mode.add_argument("--show", metavar="ID", help="print one buffer")
    ap.add_argument("--no-redact", action="store_true", help="show personal data (VIN, addresses)")
    args = ap.parse_args(argv)

    buffers = load_buffers(args.source)
    if not buffers:
        raise SystemExit("no RAMDISK_SPY buffers found in %s" % args.source)
    clean = (lambda s: s) if args.no_redact else redact

    if args.list:
        for bid in sorted(buffers):
            blob = buffers[bid]
            desc = KNOWN.get(bid) or (
                first_line(as_text(blob))[:70] if is_text(blob) else "(binary)"
            )
            print("%-16s %8d  %s" % (bid, len(buffers[bid]), clean(desc)))
        return 0
    if args.show:
        if args.show not in buffers:
            raise SystemExit("no buffer %s (see --list)" % args.show)
        print(clean(as_text(buffers[args.show])))
        return 0
    if args.aux:
        for line in aux_lines(buffers):
            print(clean(line))
        return 0

    if "25300" not in buffers:
        raise SystemExit("no C_MGR_SRC buffer (25300) in this capture")
    for line in boot_report(parse_mgr_src(as_text(buffers["25300"]))):
        print(clean(line))
    return 0


if __name__ == "__main__":
    sys.exit(main())
