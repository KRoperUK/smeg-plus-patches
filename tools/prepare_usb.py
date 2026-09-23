#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = []

"""Put a built package onto a USB stick, and prove it landed.

Getting the package onto the stick is the last manual step, and it has already gone wrong
twice: a stick was pulled mid-copy, and `ditto` left AppleDouble `._*` files beside the
package. A silently truncated copy produces an update failure in the car that looks like a
firmware fault, which is an expensive way to find out. This makes both failures loud:

  1. probe the target — the updater wants **MBR + FAT32**, and says how to fix it otherwise
  2. check free space against the package
  3. copy, excluding AppleDouble and `.DS_Store`, using a data-only copy so no `._*` is
     created in the first place
  4. **re-read every file from the stick and compare checksums** against the source, which
     is what catches the mid-copy removal
  5. confirm the layout the updater looks for, and count any `._*` left behind as a failure

It only ever writes inside `--target`, and it prints the target before touching anything.

usage:
    python3 tools/prepare_usb.py --package out/SMEG_PLUS_UPG --target /Volumes/USB
    python3 tools/prepare_usb.py --package out/SMEG_PLUS_UPG --target /Volumes/USB --dry-run
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import zlib

# macOS writes these beside a file when it copies extended attributes. The updater does not
# expect them, and on a FAT stick they are pure litter.
APPLEDOUBLE = "._"
JUNK_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}

# what the updater resolves against the stick: /bd0/SMEG_PLUS_UPG/ctrl.bin and friends
REQUIRED_FILES = ("ctrl.bin", "contract.dat")
MODULE_IMAGE = os.path.join("AppBin", "f_BigQuick.bin")


def crc32(path):
    """CRC32 of a file, read in chunks so a large image does not land in memory."""
    c = 0
    with open(path, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            c = zlib.crc32(b, c)
    return c & 0xFFFFFFFF


def is_junk(name):
    return name.startswith(APPLEDOUBLE) or name in JUNK_NAMES


def count_junk(root):
    """Every AppleDouble or editor-turd file under `root`."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        for n in list(dirnames):
            if is_junk(n):
                found.append(os.path.join(dirpath, n))
        for n in filenames:
            if is_junk(n):
                found.append(os.path.join(dirpath, n))
    return found


def check_layout(root):
    """Problems with the layout the updater expects, as a list of human-readable strings."""
    problems = []
    for rel in REQUIRED_FILES:
        if not os.path.isfile(os.path.join(root, rel)):
            problems.append("missing %s (the updater resolves it before anything else)" % rel)

    modules = (
        [n for n in os.listdir(root) if os.path.isdir(os.path.join(root, n)) and not is_junk(n)]
        if os.path.isdir(root)
        else []
    )
    if not modules:
        problems.append("no module directory (expected one containing AppBin/f_BigQuick.bin)")
    for m in modules:
        if not os.path.isfile(os.path.join(root, m, MODULE_IMAGE)):
            problems.append("%s has no %s" % (m, MODULE_IMAGE))

    if (
        not [n for n in os.listdir(root) if n.endswith("_ctrl.bin")]
        if os.path.isdir(root)
        else True
    ):
        problems.append("no *_ctrl.bin module manifest")
    return problems


def dir_size(root):
    total = 0
    for dirpath, _, filenames in os.walk(root):
        for n in filenames:
            p = os.path.join(dirpath, n)
            if not os.path.islink(p):
                total += os.path.getsize(p)
    return total


def copy_tree(src, dst):
    """Copy `src` into `dst/<basename(src)>`, skipping junk and without copying metadata.

    `shutil.copyfile` rather than `copy2`: on macOS `copy2` carries extended attributes
    across, and on a FAT target those become the `._*` files this is trying to avoid. Copying
    the data alone is the whole point.
    """
    top = os.path.join(dst, os.path.basename(src.rstrip(os.sep)))
    names = []
    for dirpath, dirnames, filenames in os.walk(src):
        rel = os.path.relpath(dirpath, src)
        dirnames[:] = [d for d in dirnames if not is_junk(d)]
        filenames = [f for f in filenames if not is_junk(f)]
        target_dir = top if rel == "." else os.path.join(top, rel)
        os.makedirs(target_dir, exist_ok=True)
        for n in filenames:
            shutil.copyfile(os.path.join(dirpath, n), os.path.join(target_dir, n))
            names.append(os.path.join(rel, n) if rel != "." else n)
    return top, names


def verify_copy(src, dst):
    """Re-read both sides and compare checksums. Returns the files that differ."""
    bad = []
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if not is_junk(d)]
        for n in filenames:
            if is_junk(n):
                continue
            s = os.path.join(dirpath, n)
            d = os.path.join(dst, os.path.relpath(s, src))
            if not os.path.isfile(d):
                bad.append((os.path.relpath(s, src), "not on the stick"))
            elif crc32(s) != crc32(d):
                bad.append((os.path.relpath(s, src), "checksum differs - copy is truncated?"))
    return bad


def probe_target(target):
    """Best-effort filesystem and partition-scheme facts. Missing facts are not failures.

    Deliberately conservative: `None` means "could not tell", and the caller only refuses on a
    value it is sure about. A probe that guesses would refuse a perfectly good stick, which is
    worse than not checking at all — and this runs on removable media, where a wrong refusal
    sends someone off to reformat a disk for no reason.
    """
    info = {"filesystem": None, "scheme": None, "note": None}
    if sys.platform != "darwin":
        info["note"] = "partition/filesystem probing is implemented for macOS only"
        return info

    def diskutil(*a):
        return subprocess.run(["diskutil", *a], capture_output=True, text=True, timeout=15).stdout

    try:
        dev = (
            subprocess.run(["df", "-P", target], capture_output=True, text=True, timeout=15)
            .stdout.splitlines()[-1]
            .split()[0]
        )
    except (OSError, subprocess.SubprocessError, IndexError) as e:
        info["note"] = "could not locate the device for %s: %s" % (target, e)
        return info

    try:
        for line in diskutil("info", dev).splitlines():
            if "File System Personality:" in line:
                info["filesystem"] = line.split(":", 1)[1].strip()
    except (OSError, subprocess.SubprocessError) as e:
        info["note"] = "could not probe the target: %s" % e
        return info

    # The scheme belongs to the whole disk, not the slice: /dev/disk4s1 -> /dev/disk4. The
    # marker strings are what `diskutil list` prints, and are the only reliable signal —
    # the volume's own "Content" field describes APFS containers and the like, not the map.
    whole = re.sub(r"s\d+$", "", dev)
    try:
        listing = diskutil("list", whole)
    except (OSError, subprocess.SubprocessError):
        listing = ""
    if "FDisk_partition_scheme" in listing:
        info["scheme"] = "MBR"
    elif "GUID_partition_scheme" in listing:
        info["scheme"] = "GPT"
    elif "Apple_partition_scheme" in listing:
        info["scheme"] = "Apple"
    return info


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--package", required=True, help="the built package directory")
    ap.add_argument("--target", required=True, help="the mounted USB stick")
    ap.add_argument("--dry-run", action="store_true", help="check everything, copy nothing")
    ap.add_argument("--force", action="store_true", help="continue past filesystem warnings")
    args = ap.parse_args(argv)

    src = os.path.abspath(args.package)
    dst = os.path.abspath(args.target)

    # Say what is about to be written, before writing anything.
    print("package : %s" % src)
    print("target  : %s" % dst)

    if not os.path.isdir(src):
        raise SystemExit("package directory does not exist: %s" % src)
    if not os.path.isdir(dst):
        raise SystemExit("target is not a directory: %s" % dst)
    if src == dst or src.startswith(dst + os.sep):
        raise SystemExit("refusing to copy the package into itself")
    if not os.path.ismount(dst) and dst.count(os.sep) < 3:
        raise SystemExit(
            "target %s is not a mount point - point --target at the stick, not a folder" % dst
        )

    # 1. the layout the updater will look for
    problems = check_layout(src)
    if problems:
        for p in problems:
            print("  layout   %s" % p)
        raise SystemExit("package layout is not what the updater expects")

    # 2. the target itself
    info = probe_target(dst)
    if info["note"]:
        print("  target   %s" % info["note"])
    print(
        "  target   filesystem=%s scheme=%s"
        % (info["filesystem"] or "unknown", info["scheme"] or "unknown")
    )
    if (
        info["filesystem"]
        and "FAT32" not in info["filesystem"]
        and "MS-DOS" not in info["filesystem"]
    ):
        msg = (
            "target is %s, not FAT32 - the updater needs MBR + FAT32 "
            "(see docs/FLASHING.md for the Disk Utility steps)" % info["filesystem"]
        )
        if not args.force:
            raise SystemExit(msg)
        print("  warning  %s" % msg)
    if info["scheme"] and "MBR" not in info["scheme"] and "FDisk" not in info["scheme"]:
        msg = "target partition scheme is %s, not MBR" % info["scheme"]
        if not args.force:
            raise SystemExit(msg)
        print("  warning  %s" % msg)

    # 3. space
    need = dir_size(src)
    free = shutil.disk_usage(dst).free
    print("  size     %.1f MB needed, %.1f MB free" % (need / 1e6, free / 1e6))
    if need > free:
        raise SystemExit("not enough space on the target: %.1f MB free" % (free / 1e6))

    if args.dry_run:
        print("dry run: nothing copied")
        return 0

    # 4. copy, then re-read every byte from the stick
    top, names = copy_tree(src, dst)
    print("  copied   %d file(s) to %s" % (len(names), top))

    bad = verify_copy(src, top)
    for rel, why in bad:
        print("  FAILED   %s: %s" % (rel, why))
    if bad:
        raise SystemExit(
            "the copy does not match the source - do not flash this stick.\n"
            "  This is what a stick pulled mid-copy looks like. Re-run to copy again."
        )

    # 5. junk is a failure, not a warning: the updater does not expect it
    junk = count_junk(dst)
    if junk:
        for j in junk[:10]:
            print("  junk     %s" % os.path.relpath(j, dst))
        raise SystemExit(
            "%d AppleDouble/editor file(s) on the stick - the updater does not expect them.\n"
            "  Remove them (macOS: dot_clean %s) and re-run." % (len(junk), dst)
        )

    print("  verified %d file(s), no junk, layout intact" % len(names))
    print("stick ready: %s" % top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
