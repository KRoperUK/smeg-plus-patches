"""`tools/dbschema.py` reads the schema of a database, one we build here.

No firmware and no vendor file is needed: the fixture is a SQLite database built in-test, the
same way `media_helpers.up_common_bytes()` builds one, but shaped to exercise every part of the
dump - a composite primary key, a NOT NULL default, an index, a UNIQUE index and a foreign key.
"""

import gzip
import io
import json
import os
import sqlite3
import subprocess
import sys
import tarfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOL = os.path.join(ROOT, "tools", "dbschema.py")

DDL = """
CREATE TABLE UP_Keys (
  Section TEXT NOT NULL,
  Name TEXT NOT NULL,
  Type INT DEFAULT 0,
  Idx INT,
  IntValue INT,
  FloatValue REAL,
  StringValue TEXT,
  BlobValue BLOB,
  reset_factory_enabled INT DEFAULT 0,
  modified INT DEFAULT 0,
  PRIMARY KEY (Section, Name)
);
CREATE TABLE other (
  id INTEGER PRIMARY KEY,
  k TEXT REFERENCES UP_Keys(Name) ON DELETE CASCADE
);
CREATE INDEX ix_type ON UP_Keys(Type);
CREATE UNIQUE INDEX ux_name ON UP_Keys(Name);
"""


def make_database(path):
    con = sqlite3.connect(path)
    con.executescript(DDL)
    con.commit()
    con.close()
    return path


def run(*args):
    return subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True)


@pytest.fixture()
def database(tmp_path):
    return make_database(tmp_path / "up_common.sqlite")


def table(entry, name):
    return next(t for t in entry["tables"] if t["name"] == name)


def column(entry, table_name, column_name):
    return next(c for c in table(entry, table_name)["columns"] if c["name"] == column_name)


def test_schema_reports_columns_types_and_keys(database):
    r = run("schema", str(database), "--json")
    assert r.returncode == 0, r.stderr
    (db,) = json.loads(r.stdout)["databases"]

    assert column(db, "UP_Keys", "Section")["not_null"] is True
    assert column(db, "UP_Keys", "Section")["primary_key"] == 1
    assert column(db, "UP_Keys", "FloatValue")["type"] == "REAL"
    assert column(db, "UP_Keys", "BlobValue")["type"] == "BLOB"
    assert column(db, "UP_Keys", "Type")["default"] == "0"
    assert column(db, "UP_Keys", "Idx")["default"] is None
    assert table(db, "UP_Keys")["primary_key"] == ["Section", "Name"]


def test_schema_reports_indexes_and_foreign_keys(database):
    r = run("schema", str(database), "--json")
    (db,) = json.loads(r.stdout)["databases"]

    keys = table(db, "other")
    assert keys["indexes"] == []  # PRIMARY KEY is reported as the key, not as an autoindex
    assert keys["foreign_keys"] == [
        {
            "table": "UP_Keys",
            "from": "k",
            "to": "Name",
            "on_update": "NO ACTION",
            "on_delete": "CASCADE",
        }
    ]

    up_indexes = {i["name"]: i for i in table(db, "UP_Keys")["indexes"]}
    assert up_indexes["ix_type"]["columns"] == ["Type"]
    assert up_indexes["ix_type"]["unique"] is False
    assert up_indexes["ux_name"]["unique"] is True


def test_text_output_names_every_table(database):
    r = run("schema", str(database))
    assert r.returncode == 0, r.stderr
    assert "table UP_Keys" in r.stdout
    assert "table other" in r.stdout
    assert "primary key: (Section, Name)" in r.stdout
    assert "NOT NULL" in r.stdout


def test_sql_flag_prints_the_create_statement(database):
    r = run("schema", str(database), "--sql")
    assert r.returncode == 0, r.stderr
    assert "CREATE TABLE UP_Keys" in r.stdout


def test_a_file_that_is_not_a_database_is_reported(tmp_path):
    bad = tmp_path / "bad.sqlite"
    bad.write_bytes(b"not a database")
    r = run("schema", str(bad))
    assert r.returncode == 1
    assert "not a database" in r.stderr


def test_a_gzipped_live_store_is_read(database, tmp_path):
    # the live up_common/up_user stores are gzip'd on disk; the tool reads them as-is
    gz = tmp_path / "up_common.sqlite"
    gz.write_bytes(gzip.compress(database.read_bytes(), 6))
    r = run("schema", str(gz), "--json")
    assert r.returncode == 0, r.stderr
    (db,) = json.loads(r.stdout)["databases"]
    assert table(db, "UP_Keys")["primary_key"] == ["Section", "Name"]


def build_partition(root, module="NAV"):
    """A gzipped tar holding two Data_base/sqlite databases and one unrelated file."""
    dbs = {}
    for name in ("up_common.sqlite", "cheatcodes.sqlite"):
        p = root / name
        make_database(p)
        dbs[name] = p.read_bytes()

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tf:
        for name, data in dbs.items():
            ti = tarfile.TarInfo("Data_base/sqlite/" + name)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
        ti = tarfile.TarInfo("ring_tones/ring1RT.wav")
        ti.size = 1
        tf.addfile(ti, io.BytesIO(b"x"))
    bin_bytes = gzip.compress(buf.getvalue(), 6)

    mod = root / module
    mod.mkdir()
    (mod / "system.bin").write_bytes(bin_bytes)
    return mod, bin_bytes


def test_from_package_reads_every_database_in_the_tar(tmp_path):
    mod, _ = build_partition(tmp_path)
    r = run("from-package", str(mod / "system.bin"), "--json")
    assert r.returncode == 0, r.stderr
    dbs = json.loads(r.stdout)["databases"]
    assert sorted(d["source"].rsplit(":", 1)[1] for d in dbs) == [
        "Data_base/sqlite/cheatcodes.sqlite",
        "Data_base/sqlite/up_common.sqlite",
    ]
    # the tone is not a database, so it is not in the report
    assert all("ring_tones" not in d["source"] for d in dbs)


def test_from_package_accepts_a_module_directory(tmp_path):
    mod, _ = build_partition(tmp_path)
    r = run("from-package", str(mod), "--json")
    assert r.returncode == 0, r.stderr
    assert len(json.loads(r.stdout)["databases"]) == 2


def test_from_package_accepts_an_extracted_tree(tmp_path):
    tree = tmp_path / "media" / "Data_base" / "sqlite"
    tree.mkdir(parents=True)
    make_database(tree / "up_common.sqlite")
    r = run("from-package", str(tmp_path / "media"), "--json")
    assert r.returncode == 0, r.stderr
    (db,) = json.loads(r.stdout)["databases"]
    assert db["source"].endswith("up_common.sqlite")
    assert table(db, "UP_Keys")["primary_key"] == ["Section", "Name"]


def test_from_package_says_so_when_there_are_no_databases(tmp_path):
    # a readable partition that simply holds no databases
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tf:
        ti = tarfile.TarInfo("ring_tones/ring1RT.wav")
        ti.size = 1
        tf.addfile(ti, io.BytesIO(b"x"))
    mod = tmp_path / "NAV"
    mod.mkdir()
    (mod / "system.bin").write_bytes(gzip.compress(buf.getvalue(), 6))
    r = run("from-package", str(mod))
    assert r.returncode != 0
    assert "no Data_base/sqlite" in (r.stderr + r.stdout)
