#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = []

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


def load_symbols(path):
    """address -> name. Header and section lines are skipped, not guessed at."""
    syms = {}
    with open(path, "r", errors="replace") as fh:
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
