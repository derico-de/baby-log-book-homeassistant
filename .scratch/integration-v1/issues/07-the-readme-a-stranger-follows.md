# 07 — The README a stranger follows

**What to build:** The document that gets somebody who has never seen this project from a fresh Home Assistant to a working wall panel that does something. It carries the hand-off the whole design rests on: the app states when things are due, and the Household writes what its home does about it.

Spec §8 (section by section, with the YAML) and §7.3 (the table).

**Blocked by:** 04 — Sixteen entities stand for a Baby; 05 — Six buttons and two services.

**Status:** ready-for-agent

- [ ] What it is, in two sentences, including the sentence about the automation engine.
- [ ] Install, claim, revoke and **re-bind** — re-bind in the same words as the lost phone.
- [ ] A stock tile-card example carrying the **`name:` override at least once**: long compound names truncate on narrow tiles, and that is a dashboard-authoring concern rather than a naming mistake.
- [ ] **Two copy-paste automations** — a chime before the bottle's life runs out, and an announcement when a feed comes due. The lead time is the family's, written in their trigger; the app never sends one.
- [ ] Both automations carry the **caregiving condition by default**, with a sentence saying that switching Caregiving off in the app quiets them. This is how that switch reaches a wall.
- [ ] A **script example** giving a one-press bottle button, targeting the Baby's device.
- [ ] The **non-goals**, each with a one-line reason. A stranger should not have to open an ADR to learn there is no custom card.
- [ ] The **three-column compatibility table**: integration / needs server / needs Home Assistant.
- [ ] **Blueprints are out of scope** — copy-paste examples, not a blueprint library.
- [ ] The server repo's README gains **one link** to the compatibility table.
- [ ] A line under `## [Unreleased]` in `CHANGELOG.md`, same commit.
