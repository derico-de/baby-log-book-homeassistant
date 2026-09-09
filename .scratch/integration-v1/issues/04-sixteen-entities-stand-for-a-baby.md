# 04 — Sixteen entities stand for a Baby

**What to build:** The read surface, and the highest-leverage thing in this repo: get it right and the dashboard is stock tile cards, and every automation a family writes couples to it — so changing it later breaks other people's homes.

Spec §6.5 (the three entity tables and the existence rules) and §6.8 (the name table in three languages).

**Blocked by:** 03 — The coordinator keeps a live picture.

**Status:** ready-for-agent

- [ ] **One device per Baby**, named as the Household spelled her, plus **one Household device**. A Baby added after setup appears without re-adding the integration; a deleted Baby's device goes stale and removable.
- [ ] Sixteen entities per Baby: **7 timestamps**, **3 binaries**, **6 totals** — keys byte-for-byte the payload's field names.
- [ ] Timestamps carry the timestamp device class, so the frontend renders them **relative, live and localized** for free. Do not compute "8 minutes ago" by hand.
- [ ] The three binaries take **no device class** — none fits, and the translated names carry the meaning. They are the automation *conditions* where the timestamps are the *triggers*.
- [ ] The six totals declare their reset at the Household's Day Start instant from the payload. A sensor must **never** re-derive "today" from local midnight.
- [ ] Two entities on the Household device: a **diagnostic** last-update timestamp (the coordinator's own "when did I last hear the server" — the staleness tell availability cannot express), and a **caregiving** binary sensor.
- [ ] Entities **exist with state unknown** when inapplicable — a cleared Target must never break a family's dashboard. The exception is the appear-on-first-use pair, created from what the payload carries and **never removed once created**.
- [ ] Names translated in **en, de and ro** from the table in spec §6.8 — never hardcoded English. The Romanian cells marked in that table ship as coined; the native pass is a pre-1.0.0 item.
- [ ] A line under `## [Unreleased]` in `CHANGELOG.md`, same commit.
