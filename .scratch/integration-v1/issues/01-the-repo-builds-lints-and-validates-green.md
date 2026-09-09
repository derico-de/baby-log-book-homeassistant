# 01 — The repo builds, lints and validates green

**What to build:** The scaffold every other ticket lands into: the packaging, the tooling and the two workflows, with an importable but empty integration behind them. Nothing user-facing — this ticket is done when a pull request goes green.

Spec §6.1 (layout, manifest keys) and §6.10 (the workflows, verbatim).

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `pyproject.toml` under **`uv`** — `uv run <tool>`, never a venv and never a global.
- [ ] Ruff, mypy in **strict** mode, and `pytest-homeassistant-custom-component`. **No live Home Assistant instance**, ever, in tests.
- [ ] `manifest.json` with domain **`baby_log_book`** (immutable once entries exist in the wild), name **Baby Log Book**, `config_flow: true`, `integration_type: device`, `iot_class: local_push`. `hacs.json` with the same name.
- [ ] `ci.yml` on push to `main`, on pull requests, and on a **weekly cron**. Three hard-gate jobs: `lint`, `test` (coverage floor **95 %**), `validate` (hassfest with no inputs, plus `hacs/action` with `category: integration` and `ignore: brands`).
- [ ] `release.yml` on `v*.*.*` tags: **refuse** the release when the manifest version disagrees with the tag, then publish with the body taken from that version's `CHANGELOG.md` section. **Enforced, never stamped** — a manifest rewritten from the tag leaves the version in the tree meaningless for anyone installing from the default branch.
- [ ] Actions pinned by **major tag**, not SHA. Dependabot weekly on `pip` and `github-actions`.
- [ ] **One** pinned Home Assistant version, tracked weekly — and it is the declared floor. Never claim a floor you do not test. No matrix, **no beta job**.
- [ ] `ignore: brands` carries a comment marking it a **dated debt**, pointing at the pre-1.0.0 checklist.
- [ ] **`CHANGELOG.md` is created here**, with an `## [Unreleased]` section — `AGENTS.md`
      requires a line per change and every later ticket assumes the file exists. Its
      sections are what `release.yml` publishes as release notes, so the two cannot drift.
- [ ] A line under `## [Unreleased]` in `CHANGELOG.md`, same commit.
