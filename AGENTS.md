# baby-log-book-homeassistant

## What this repo is

The Home Assistant custom integration for Baby Log Book. The server it talks to
lives in the sibling checkout `../baby-log-book`; both halves are AGPL-3.0-or-later
and share no code — the wire shapes are re-stated here and implemented fresh in
Python.

The specification for both halves is
`../baby-log-book/.scratch/home-assistant/spec.md`. Read it before writing code;
it is precise enough to build from without inheriting the server repo's habits.

## Rules

- **The domain is `baby_log_book` and it is immutable.** Config entries in the
  wild are keyed by it. What a user *sees* is **Baby Log Book** — `manifest.json
  → name` and `hacs.json → name`.
- **Vocabulary comes from `../baby-log-book/CONTEXT.md`.** Household, Member,
  Caregiver, Hub, Claim Link, Notice, Day Start are defined there and are never
  redefined here. User-facing strings follow the app's own words, in en, de and ro.
- **`manifest.json → version` = git tag = GitHub release.** They are bumped in
  one commit and CI refuses a release where they disagree
  ([ADR-0039](../baby-log-book/docs/adr/0039-the-integration-gates-on-the-server-release.md)).
- **A wire change lands server-side first**, backward-compatibly. Only then may
  an integration release raise its baked-in `MIN_SERVER_VERSION`.
- **Decisions that are hard to reverse get an ADR** — in the public server repo
  when they govern the product, here when they govern only the integration.
- **Every change adds a line under `## [Unreleased]` in `CHANGELOG.md`**, in the
  same commit. A release renames that section.
- **This repo lives inside the mounted workspace.** A sibling repo was lost once
  by living outside it. Commit early; the maintainer pushes from outside the
  sandbox.

## Issue tracker

Issues and specs live as markdown under `.scratch/<feature-slug>/`, following
`../baby-log-book/docs/agents/issue-tracker.md`.
