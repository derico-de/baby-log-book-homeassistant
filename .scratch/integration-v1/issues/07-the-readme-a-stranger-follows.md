# 07 — The README a stranger follows

**What to build:** The document that gets somebody who has never seen this project from a fresh Home Assistant to a working wall panel that does something. It carries the hand-off the whole design rests on: the app states when things are due, and the Household writes what its home does about it.

Spec §8 (section by section, with the YAML) and §7.3 (the table).

**Blocked by:** 04 — Sixteen entities stand for a Baby; 05 — Six buttons and two services.

**Status:** resolved

- [x] What it is, in two sentences, including the sentence about the automation engine.
- [x] Install, claim, revoke and **re-bind** — re-bind in the same words as the lost phone.
- [x] A stock tile-card example carrying the **`name:` override at least once**: long compound names truncate on narrow tiles, and that is a dashboard-authoring concern rather than a naming mistake.
- [x] **Two copy-paste automations** — a chime before the bottle's life runs out, and an announcement when a feed comes due. The lead time is the family's, written in their trigger; the app never sends one.
- [x] Both automations carry the **caregiving condition by default**, with a sentence saying that switching Caregiving off in the app quiets them. This is how that switch reaches a wall.
- [x] A **script example** giving a one-press bottle button, targeting the Baby's device.
- [x] The **non-goals**, each with a one-line reason. A stranger should not have to open an ADR to learn there is no custom card.
- [x] The **three-column compatibility table**: integration / needs server / needs Home Assistant.
- [x] **Blueprints are out of scope** — copy-paste examples, not a blueprint library.
- [x] The server repo's README gains **one link** to the compatibility table.
- [x] A line under `## [Unreleased]` in `CHANGELOG.md`, same commit.

## Comments

**Built.** `README.md` here, and the one link from the server repo's `README.md`
into the compatibility table.

One note: **the compatibility table's first row reads `_unreleased_`**, with the
two floors filled in — server ≥ 1.25.0, Home Assistant ≥ 2026.8.3 — because both
numbers are already true and only the integration's own has nothing to say yet.
`manifest.json → version` is `0.0.0` for the same reason; the first release bumps
both in one commit, and `release.yml` refuses a tag that disagrees.

**Review follow-up — one item deferred.** Spec §8.3 asks for **one screenshot** of
a Parent minting an Invite *for a Hub*. It is not in the README: taking it needs
a running deployment and a real Settings screen, which is ticket 08's ground and
not something a mocked suite can produce. Everything else in §8 is there. Capture
it while ticket 08 is being walked through, and drop it into §3 of the README.
