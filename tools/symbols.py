#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

"""Reading the symbol maps the vendor's unstripped ELFs come with.

The format is `<hex address> <type> <name>`, one per line — `nm` output, and the maps carry
section headers and blank lines whose first field is not an address. Aliases (several names at
one address) do occur, and **the last one wins**; that is what the analysis tools have always
done, so it is what this does.

This exists because the parser had been copied into `ppcdis`, `xref` and `callers`, and a
fourth copy went into `symdiff` that differed in a way nobody would have noticed: it used
`setdefault`, so a duplicate address resolved to the *first* name where the other three
resolved to the last. Two tools reading the same map and disagreeing about what a symbol is
called is precisely the kind of trap this repository exists to avoid, and it is invisible
until it bites.

Shared here so there is one answer. `AGENTS.md` notes these analysis tools are themselves
untested — see issue #38 — so the tests for this module are the closest thing they have.
"""

import gzip
import struct

# --- the VxWorks symbol table inside a raw kernel image ---------------------
#
# `BSP/SMEG_PLUS_512/vxWorks.bin` is not an ELF: it is a raw PowerPC image based at 0x00200000
# that carries a VxWorks symbol table. *(executed, tests/test_firmware_bsp.py, never in CI)* on
# the shipped image the table is at file offset 0x622024 - the address 0x00822024 that
# bousqi/SMEG_PLUS records for `vxSymTbl` - holding 13 854 entries of 20 bytes, and it names
# 0x0058c248 `tickGet` and 0x00484a94 `logMsg`, the two kernel addresses this repository's
# patches branch to. So the base and the 20-byte stride are this repository's own, not a third
# party's. Everything else is bousqi's description of `struct s_Symbol` and is tagged as read:
# the two middle words (every shipped entry has 0 in both), and the four `type` codes - whose
# low bits are bousqi's, with a constant `0x100` set in the word (see `VXWORKS_TYPE_NAMES`).
VXWORKS_BASE = 0x00200000
VXWORKS_ENTRY_SIZE = 20
# bousqi/SMEG_PLUS (`VXWORKS.md`) gives the codes as `0x100 unk, 0x400 func, 0x800 data,
# 0x1000 ext`. On the shipped image the `+0x10` word is one of those kind bits *or* `0x100` -
# 0x300, 0x500, 0x900, 0x1100 and nothing else, over all 13 854 entries - so those are the words
# this maps, and the kind bits are what carries the meaning: 0x400-kind addresses start with an
# instruction (`tickGet`, `logMsg`, `getUBootVersion`), 0x800-kind ones hold data
# (`g_UBootVersion`), and 0x1000-kind addresses lie outside the image, which is what "ext" is.
VXWORKS_TYPE_NAMES = {0x300: "unk", 0x500: "func", 0x900: "data", 0x1100: "ext"}
_NAME_LIMIT = 96  # longest plausible symbol name; bounds the search for its NUL


def _read_name(image, ptr, base):
    """The NUL-terminated printable string a name pointer resolves to, or None.

    A pointer that lands outside the image, on a NUL, or on anything with a byte outside
    `0x21..0x7e` is not a name. That single test is what tells a table apart from the
    surrounding image, so it is deliberately the only thing trusted.
    """
    off = ptr - base
    if off < 0 or off >= len(image):
        return None
    end = image.find(b"\x00", off, off + _NAME_LIMIT)
    if end <= off:
        return None
    raw = image[off:end]
    if not all(0x20 < b < 0x7F for b in raw):
        return None
    return raw.decode("ascii")


def _is_table_entry(image, at, base):
    """Whether the 20 bytes at `at` look like a `s_Symbol` rather than image data that happens to.

    Requires a readable name *and* the two zero words. The shape is what stops a backward walk
    latching onto the string area in front of the table, whose words are string offsets and
    therefore point at printable text by construction. *(executed)* all 13 854 entries of the
    shipped table carry 0 in both words; a table that carries something else there is still read
    when its `offset` is given.
    """
    unk1, name_ptr, _address, unk2, _typ = struct.unpack_from(">5I", image, at)
    return unk1 == 0 and unk2 == 0 and _read_name(image, name_ptr, base) is not None


def find_vxworks_symtab(blob, base=VXWORKS_BASE, min_run=8, max_gap=64):
    """File offset of the table's first entry, or None.

    The table has no signature to look for, so the only handle is that consecutive entries
    resolve their name pointers. `min_run` is what stops a coincidental pair of words in
    ordinary image data being taken for a table; eight consecutive entries that each resolve
    is not something the rest of an image does by accident.

    A real table is not one unbroken run, though. *(executed)* 33 of the shipped image's
    13 854 entries have a name pointer that resolves to nothing, in gaps of up to 11 entries,
    all in the middle of the table. A scan that took the longest *unbroken* run would therefore
    start ~4 000 entries in and hand back about two thirds of the symbols - which is what this
    did before the image was available to check it against. So the longest run is only a seed:
    the start is then walked back over gaps of up to `max_gap` entries, the same tolerance
    `iter_vxworks_symtab` walks forward with, and the walk stops at the entry shape (see
    `_is_table_entry`). Entries are tried at 4-byte alignment, which is where the table is on the
    images seen. Pass an explicit offset to `load_vxworks_symtab` to skip this scan entirely.
    """
    image = bytes(blob)
    end = len(image) - VXWORKS_ENTRY_SIZE
    best_off, best_run = None, 0
    off = 0
    while off <= end:
        run = 0
        while off + run * VXWORKS_ENTRY_SIZE <= end:
            at = off + run * VXWORKS_ENTRY_SIZE
            if _read_name(image, struct.unpack_from(">I", image, at + 4)[0], base) is None:
                break
            run += 1
        if run > best_run:
            best_off, best_run = off, run
        # a run measured from here is the longest one starting here, so nothing inside it can
        # beat it; with no run at all, move on by one word
        off += run * VXWORKS_ENTRY_SIZE if run else 4

    if best_run < min_run:
        return None

    start = best_off
    while True:
        back = None
        for gap in range(1, max_gap + 1):
            at = start - gap * VXWORKS_ENTRY_SIZE
            if at < 0:
                break
            if _is_table_entry(image, at, base):
                back = at
                break
        if back is None:
            break
        start = back
    return start


def iter_vxworks_symtab(blob, offset, base=VXWORKS_BASE, count=None, max_gap=64):
    """Yield `(address, name, type)` for the table at `offset`, skipping entries it cannot read.

    Tolerant on purpose. An entry whose name pointer does not resolve to a printable string is
    stepped over rather than ending the walk, because one unreadable entry in 13 000 should not
    cost the other 12 999 — the walk stops only after `max_gap` consecutive misses, which is
    what the end of the table looks like. `count` caps how many entries are examined, since a
    table's length is not recorded anywhere the table itself points at.

    The type word is returned, not filtered on: the four codes are a third-party description,
    and an entry with a type nobody has described should not have its name hidden. One
    consequence of the same tolerance is worth knowing: the string area that follows the table
    can hold words that resolve, so a walk that starts at the table and never meets a run of
    `max_gap` misses may report a handful of names past the table's real end. `count` bounds it.
    """
    image = bytes(blob)
    end = len(image) - VXWORKS_ENTRY_SIZE
    examined = 0
    gap = 0
    while offset <= end:
        _unk1, name_ptr, address, _unk2, typ = struct.unpack_from(">5I", image, offset)
        name = _read_name(image, name_ptr, base)
        if name is None:
            gap += 1
            if gap > max_gap:
                break
        else:
            gap = 0
            yield address, name, typ
        examined += 1
        if count is not None and examined >= count:
            break
        offset += VXWORKS_ENTRY_SIZE


def load_vxworks_symtab(blob, base=VXWORKS_BASE, offset=None, count=None, max_gap=64):
    """`address -> name` from the VxWorks symbol table in a raw kernel image.

    `blob` is the image as it comes off the stick and `base` the address it is loaded at, so a
    name pointer `p` is read at file offset `p - base`; the same base the addresses are reported
    in. With no `offset` the table is located by scanning (`find_vxworks_symtab`) and an image
    that holds no table returns `{}` rather than raising.

    As in `load_symbols`, **the last name at an address wins** — the two readers must not
    disagree about what an address is called. `extents()` and `name_at()` take this dict
    unchanged, so a kernel address can be named the same way an application one is.

    *(executed)* On `BSP/SMEG_PLUS_512/vxWorks.bin` this returns 13 564 names from a table of
    13 854 entries, and `[0x0058C248]` is `tickGet`.
    """
    if offset is None:
        offset = find_vxworks_symtab(blob, base=base, max_gap=max_gap)
        if offset is None:
            return {}

    syms = {}
    for address, name, _typ in iter_vxworks_symtab(
        blob, offset, base=base, count=count, max_gap=max_gap
    ):
        syms[address] = name
    return syms


def _open(path):
    """Open a map as text, whether it is plain or the `.gz` the unit ships."""
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt", errors="replace")
    return open(path, "r", errors="replace")


def load_symbols(path):
    """address -> name. Header and section lines are skipped, not guessed at."""
    syms = {}
    with _open(path) as fh:
        for line in fh:
            p = line.split()
            if len(p) >= 3:
                try:
                    syms[int(p[0], 16)] = p[2]
                except ValueError:
                    # the symbol map has header and section lines whose first
                    # field is not a hex address; those are not symbols
                    pass
    return syms


def load_typed_symbols(path):
    """address -> (type letter, name), with the same skipping and last-wins rule.

    The survey needs the `nm` type to tell code (`T`/`W`) from data; everything else wants
    only the name, which is why this is separate rather than a change to `load_symbols`.
    """
    syms = {}
    with _open(path) as fh:
        for line in fh:
            p = line.split()
            if len(p) >= 3:
                try:
                    syms[int(p[0], 16)] = (p[1], p[2])
                except ValueError:
                    # a header or section line, as in load_symbols: not a symbol
                    pass
    return syms


def extents(syms, image_len, base):
    """name -> (start, size), size being up to the next symbol in address order.

    Symbol maps carry no sizes, so the next address is the only estimate available. It
    over-states the last symbol in a run, which is why nothing should depend on an exact size
    — and the over-statement is why `name_at` will hand back a name for an address that is
    really past the end of that function.
    """
    out = {}
    addrs = sorted(syms)
    for i, addr in enumerate(addrs):
        nxt = addrs[i + 1] if i + 1 < len(addrs) else image_len + base
        out[syms[addr]] = (addr, max(0, nxt - addr))
    return out


def name_at(ext, addr):
    """The symbol containing an address, or None. Innermost wins when extents overlap."""
    owner = None
    for name, (start, _) in ext.items():
        if start <= addr:
            if owner is None or start > ext[owner][0]:
                owner = name
    if owner is None:
        return None
    start, size = ext[owner]
    return owner if addr < start + size else None
