# 01 — The repo builds, lints and validates green

**What to build:** The scaffold every other ticket lands into: the packaging, the tooling and the two workflows, with an importable but empty integration behind them. Nothing user-facing — this ticket is done when a pull request goes green.

Spec §6.1 (layout, manifest keys) and §6.10 (the workflows, verbatim).

**Blocked by:** None — can start immediately.

**Status:** resolved

- [x] `pyproject.toml` under **`uv`** — `uv run <tool>`, never a venv and never a global.
- [x] Ruff, mypy in **strict** mode, and `pytest-homeassistant-custom-component`. **No live Home Assistant instance**, ever, in tests.
- [x] `manifest.json` with domain **`baby_log_book`** (immutable once entries exist in the wild), name **Baby Log Book**, `config_flow: true`, `integration_type: device`, `iot_class: local_push`. `hacs.json` with the same name.
- [x] `ci.yml` on push to `main`, on pull requests, and on a **weekly cron**. Three hard-gate jobs: `lint`, `test` (coverage floor **95 %**), `validate` (hassfest with no inputs, plus `hacs/action` with `category: integration` and `ignore: brands`).
- [x] `release.yml` on `v*.*.*` tags: **refuse** the release when the manifest version disagrees with the tag, then publish with the body taken from that version's `CHANGELOG.md` section. **Enforced, never stamped** — a manifest rewritten from the tag leaves the version in the tree meaningless for anyone installing from the default branch.
- [x] Actions pinned by **major tag**, not SHA. Dependabot weekly on `pip` and `github-actions`.
- [x] **One** pinned Home Assistant version, tracked weekly — and it is the declared floor. Never claim a floor you do not test. No matrix, **no beta job**.
- [x] `ignore: brands` carries a comment marking it a **dated debt**, pointing at the pre-1.0.0 checklist.
- [x] **`CHANGELOG.md` is created here**, with an `## [Unreleased]` section — `AGENTS.md`
      requires a line per change and every later ticket assumes the file exists. Its
      sections are what `release.yml` publishes as release notes, so the two cannot drift.
- [x] A line under `## [Unreleased]` in `CHANGELOG.md`, same commit.

## Comments

**Built.** `pyproject.toml` under `uv` (ruff, mypy strict, pytest), `manifest.json`,
`hacs.json`, `.github/workflows/{ci,release}.yml`, `.github/dependabot.yml`,
`CHANGELOG.md`.

Three notes:

- **The pinned Home Assistant is 2026.8.3** — `pytest-homeassistant-custom-component==0.13.357`,
  the last release before the 2026.9 line. Chosen over latest so the floor we claim
  in `hacs.json` is the version the dev-env container in the server repo actually
  runs, which is what ticket 08 will be looked at on. It also pins Python ≥ 3.14.2,
  which is `requires-python` here for no reason of ours.
- **`mypy` runs without `warn_unreachable`**, and the reason is in `pyproject.toml`:
  `DataUpdateCoordinator.data` is declared non-optional although it is `None` until
  the first refresh, so every honest guard against that reads as dead code.
- **`ruff` ignores `D401`** (imperative docstrings). This repo's prose says what a
  thing *is*, in the register the spec and the server repo are written in;
  imperative docstrings would have made every comment read in a second voice.

**Review follow-up.** `ruff`'s `target-version` is pinned to `py313`, one behind
the interpreter we run, and the reason is in `pyproject.toml`: PEP 758 lets
Python 3.14 write `except A, B:` without parentheses and the `py314` formatter
strips them, which two reviewers read as a Python 2 syntax error. Legibility cost
for nothing gained.
