# Copilot instructions

See [`AGENTS.md`](../AGENTS.md) at the repository root — it is the single source of
guidance for AI agents here.

Quick reminders, in case the model only reads this file:

- **No vendor firmware, ever.** No `.bin`/`.out`/`.mot`/symbol maps/tones committed,
  uploaded as artefacts, or attached to issues.
- **PR titles are conventional commits** — the repo squash-merges, so the title becomes
  the commit on `main` and drives Release Please. `feat:` minor, `fix:` patch,
  `feat!:`/`fix!:` major; the description starts lower case.
- **Run `pytest tests -q`, `ruff check tools tests`, `ruff format --check tools tests` and
  `zensical build --strict`** before proposing a change — what CI runs; all work without any
  firmware. Install `requirements-dev.txt`, or the emulator tests skip instead of running.
- Application patches live in `patches/*.json` — prefer adding an entry there over new
  code. Each carries its hardware `status`; `tools/patch_status.py` regenerates the tables.
- Do not claim a patch works beyond its recorded status — tag claims *executed*, *read*,
  *inferred* or *not known*.
- **Warn before a `USER_DATA` payload**: it overwrites the car's paired phones, destinations
  and presets.
- **Spy captures and settings dumps hold the VIN and personal data.** Never commit, quote
  or attach them.
