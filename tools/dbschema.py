#!/usr/bin/env python3

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

"""Dump the schema of the SQLite databases a SMEG+ unit keeps its state in.

A unit keeps its settings in ~29 SQLite databases. The seeds ship read-only in the media
partition (`Data_base/sqlite/*.sqlite`, inside `<module>/system.bin`); the live copies are on
the `/USER_DATA` partition the car owns, one `.sqlite` with a `.inf` CRC sidecar. Editing a
seed changes nothing on the unit — see docs/DATABASES.md and docs/MEDIA_PARTITION.md.

This reads a database and prints what is *in* it structurally: tables, columns and their types,
NOT NULL / defaults, the primary key, indexes and foreign keys. It reads **your own** databases
or the ones in **your own** package; it ships no vendor data. The live `up_common`/`up_user`
stores are gzip'd on disk, which is handled transparently.

Because it only reads, it never writes to the file it is given: the bytes are copied to a
throwaway location first, so a live database on `USER_DATA` is not touched and no `-wal`/`-shm`
is created beside it.

usage:
    # a database, or several
    python3 tools/dbschema.py schema path/to/up_common.sqlite

    # every Data_base/sqlite/*.sqlite inside your own media partition, straight from the
    # gzipped tar (a system.bin file) or from an extracted package/module directory
    python3 tools/dbschema.py from-package SMEG_PLUS_UPG/NAV/system.bin
    python3 tools/dbschema.py from-package SMEG_PLUS_UPG/NAV
    python3 tools/dbschema.py from-package media/

    # machine-readable, and with the original CREATE statements
    python3 tools/dbschema.py schema up_common.sqlite --json
    python3 tools/dbschema.py schema up_common.sqlite --sql
"""

import argparse
import gzip
import io
import json
import os
import re
import sqlite3
import sys
import tarfile
import tempfile
from pathlib import Path

# The seeds sit here in the tar; the same suffix is used for an extracted tree.
SQLITE_DIR = "Data_base/sqlite"
SQLITE_MEMBER = re.compile(r"(^|/)Data_base/sqlite/[^/]+\.sqlite$")

# The live up_common/up_user stores are gzip'd on disk (the boot log's gzUnixRead), so a
# database recovered from a SPYSTORE dump carries this magic rather than the SQLite header.
GZIP_MAGIC = b"\x1f\x8b"


def quote(identifier):
    """A SQL identifier, quoted so a name with a quote in it cannot break a PRAGMA."""
    return '"%s"' % identifier.replace('"', '""')


def introspect(con):
    """{tables: [...]} for one open database, in sqlite_master order."""
    tables = []
    rows = con.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'table'"
        " AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
    ).fetchall()
    for name, sql in rows:
        cols = con.execute("PRAGMA table_info(%s)" % quote(name)).fetchall()
        columns = [
            {
                "name": c[1],
                "type": c[2] or "",
                "not_null": bool(c[3]),
                "default": c[4],
                "primary_key": c[5],
            }
            for c in cols
        ]
        indexes = []
        for idx in con.execute("PRAGMA index_list(%s)" % quote(name)).fetchall():
            # (seq, name, unique, origin, partial) on modern SQLite; tolerate fewer columns
            iname = idx[1]
            if iname.startswith("sqlite_autoindex_"):
                continue  # restates a UNIQUE or PRIMARY KEY constraint; nothing new to show
            index_columns = [
                r[2] for r in con.execute("PRAGMA index_info(%s)" % quote(iname)).fetchall()
            ]
            indexes.append(
                {
                    "name": iname,
                    "unique": bool(idx[2]),
                    "origin": idx[3] if len(idx) > 3 else "",
                    "partial": bool(idx[4]) if len(idx) > 4 else False,
                    "columns": index_columns,
                }
            )
        foreign_keys = [
            {
                "table": r[2],
                "from": r[3],
                "to": r[4],
                "on_update": r[5],
                "on_delete": r[6],
            }
            for r in con.execute("PRAGMA foreign_key_list(%s)" % quote(name)).fetchall()
        ]
        tables.append(
            {
                "name": name,
                "sql": sql,
                "columns": columns,
                "primary_key": [c["name"] for c in columns if c["primary_key"]],
                "indexes": indexes,
                "foreign_keys": foreign_keys,
            }
        )
    return {"tables": tables}


def describe_bytes(data, source):
    """Introspect a database held in memory, by way of a throwaway read-only copy."""
    if data[:2] == GZIP_MAGIC:
        data = gzip.decompress(data)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "db.sqlite"
        path.write_bytes(data)
        # read-only: the copy cannot be changed, and no journal is made for it
        con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        try:
            return dict(introspect(con), source=source)
        finally:
            con.close()


def describe_file(path):
    return describe_bytes(Path(path).read_bytes(), str(path))


# ------------------------------------------------------------------ rendering


def column_line(col):
    bits = [col["type"] or "(no type)"]
    if col["not_null"]:
        bits.append("NOT NULL")
    if col["default"] is not None:
        bits.append("DEFAULT %s" % col["default"])
    if col["primary_key"]:
        bits.append("PK")
    return bits


def render_database(db, show_sql=False):
    out = ["%s  (%d tables)" % (db["source"], len(db["tables"]))]
    if not db["tables"]:
        out.append("  (no tables)")
    for table in db["tables"]:
        out.append("")
        out.append("  table %s (%d columns)" % (table["name"], len(table["columns"])))
        width = max((len(c["name"]) for c in table["columns"]), default=0)
        for col in table["columns"]:
            out.append("    %-*s  %s" % (width, col["name"], "  ".join(column_line(col))))
        if table["primary_key"]:
            out.append("    primary key: (%s)" % ", ".join(table["primary_key"]))
        for idx in table["indexes"]:
            kind = "unique index" if idx["unique"] else "index"
            note = " (%s)" % {"u": "unique constraint", "pk": "primary key"}.get(idx["origin"], "")
            out.append("    %s %s (%s)%s" % (kind, idx["name"], ", ".join(idx["columns"]), note))
        for fk in table["foreign_keys"]:
            out.append(
                "    foreign key (%s) -> %s(%s) on update %s on delete %s"
                % (fk["from"], fk["table"], fk["to"], fk["on_update"], fk["on_delete"])
            )
        if show_sql and table["sql"]:
            out.append("")
            out.extend("    " + line for line in table["sql"].splitlines())
    return "\n".join(out)


def emit(databases, as_json, show_sql):
    if as_json:
        print(json.dumps({"databases": databases}, indent=2))
        return
    for i, db in enumerate(databases):
        if i:
            print()
        print(render_database(db, show_sql=show_sql))


# ------------------------------------------------------------------- sources


def find_in_tar(blob, label):
    """(source, bytes) for every Data_base/sqlite/*.sqlite in a gzipped tar or raw tar."""
    try:
        raw = gzip.decompress(blob)
    except OSError:
        raw = blob  # already an uncompressed tar
    found = []
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as tf:
            for member in tf.getmembers():
                if member.isfile() and SQLITE_MEMBER.search(member.name):
                    found.append(("%s:%s" % (label, member.name), tf.extractfile(member).read()))
    except tarfile.TarError as e:
        raise SystemExit("%s is not a gzipped tar (is it a <module>/system.bin?): %s" % (label, e))
    return found


def find_in_tree(root):
    """(source, bytes) for every Data_base/sqlite/*.sqlite under an extracted directory."""
    found = []
    for path in sorted(Path(root).rglob("*.sqlite")):
        rel = path.relative_to(root).as_posix()
        if SQLITE_MEMBER.search(rel):
            found.append((str(path), path.read_bytes()))
    return found


def collect_from_package(target):
    """The media-partition databases in a system.bin, a module dir, or a tree of either."""
    p = Path(target)
    if p.is_file():
        return find_in_tar(p.read_bytes(), str(p))
    if p.is_dir():
        bin_ = p / "system.bin"
        if bin_.is_file():
            return find_in_tar(bin_.read_bytes(), str(bin_))
        return find_in_tree(p)
    raise SystemExit("no such file or directory: %s" % target)


# ----------------------------------------------------------------------- CLI


def cmd_schema(args):
    databases = []
    failed = []
    for name in args.files:
        if not os.path.isfile(name):
            failed.append("%s: no such file" % name)
            continue
        try:
            databases.append(describe_file(name))
        except sqlite3.Error as e:
            failed.append("%s: %s" % (name, e))
    emit(databases, args.json, args.sql)
    for f in failed:
        print(f, file=sys.stderr)
    return 1 if failed else 0


def cmd_from_package(args):
    found = collect_from_package(args.path)
    databases, failed = [], []
    for source, data in found:
        try:
            databases.append(describe_bytes(data, source))
        except sqlite3.Error as e:
            failed.append("%s: %s" % (source, e))
    if not databases and not failed:
        raise SystemExit(
            "no %s/*.sqlite found under %s — is it a SMEG+ media partition?"
            % (SQLITE_DIR, args.path)
        )
    emit(databases, args.json, args.sql)
    for f in failed:
        print(f, file=sys.stderr)
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("schema", help="dump one or more .sqlite files")
    p.add_argument("files", nargs="+", help="a .sqlite database (your own, or one you extracted)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--sql", action="store_true", help="also print each table's CREATE statement")
    p.set_defaults(fn=cmd_schema)

    p = sub.add_parser(
        "from-package",
        help="dump every Data_base/sqlite/*.sqlite in your own media partition",
    )
    p.add_argument(
        "path",
        help="a <module>/system.bin, a module directory, or an extracted media tree",
    )
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--sql", action="store_true", help="also print each table's CREATE statement")
    p.set_defaults(fn=cmd_from_package)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
