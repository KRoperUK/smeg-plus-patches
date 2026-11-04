"""Every docs page is reachable from the site nav, and every nav entry exists (#200).

`zensical build --strict` catches a broken link, but not a page that nothing links to: an
orphaned page builds fine and is simply never found.
"""

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

tomllib = pytest.importorskip("tomllib") if sys.version_info >= (3, 11) else None


def nav_pages():
    cfg = tomllib.loads((ROOT / "zensical.toml").read_text())

    def walk(x):
        if isinstance(x, str):
            yield x
        elif isinstance(x, list):
            for i in x:
                yield from walk(i)
        elif isinstance(x, dict):
            for v in x.values():
                yield from walk(v)

    return set(walk(cfg["project"]["nav"]))


@pytest.mark.skipif(tomllib is None, reason="tomllib needs Python 3.11+")
def test_no_page_is_orphaned_and_no_nav_entry_is_missing():
    docs = ROOT / "docs"
    # workshop_generated/ is local-only converter output: gitignored, built on
    # demand, and deliberately absent from the committed nav. agents/ holds
    # agent-facing notes that are published but not part of the reader nav.
    skip = {"workshop_generated", "agents"}
    pages = {
        p.relative_to(docs).as_posix()
        for p in docs.rglob("*.md")
        if not (set(p.relative_to(docs).parts) & skip)
    }
    listed = nav_pages()
    assert sorted(pages - listed) == [], "pages not in zensical.toml nav"
    assert sorted(listed - pages) == [], "nav entries with no page"
