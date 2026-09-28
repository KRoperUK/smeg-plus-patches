# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository.

**Read [AGENTS.md](AGENTS.md).** It is the single brief for AI agents here: the hard rules
(no vendor firmware anywhere, conventional commit titles, `main` is PR-only, warn before
anything that destroys the car owner's settings, do not automate the release PR approval),
how to run the tools, tests, lint and docs, how a package is put together, the analysis
workflow, and the firmware facts that are easy to get wrong. None of it is repeated here, so
that the two cannot drift apart.

The commands you will reach for most:

```sh
.venv/bin/python -m pytest tests -q                   # full suite, no firmware needed
.venv/bin/python -m ruff check tools tests
.venv/bin/python -m ruff format --check tools tests
.venv/bin/python -m zensical build --strict           # docs; a broken anchor fails it
uv run tools/build_package.py --manifest builds/aux-boot.json
```

Every tool, with its `--help`, is on the generated [docs/TOOLS.md](docs/TOOLS.md) page.
