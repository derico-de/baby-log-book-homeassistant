# 04 — Sixteen entities stand for a Baby

**What to build:** The read surface, and the highest-leverage thing in this repo: get it right and the dashboard is stock tile cards, and every automation a family writes couples to it — so changing it later breaks other people's homes.

Spec §6.5 (the three entity tables and the existence rules) and §6.8 (the name table in three languages).

**Blocked by:** 03 — The coordinator keeps a live picture.

**Status:** resolved

- [x] **One device per Baby**, named as the Household spelled her, plus **one Household device**. A Baby added after setup appears without re-adding the integration; a deleted Baby's device goes stale and removable.
- [x] Sixteen entities per Baby: **7 timestamps**, **3 binaries**, **6 totals** — keys byte-for-byte the payload's field names.
- [x] Timestamps carry the timestamp device class, so the frontend renders them **relative, live and localized** for free. Do not compute "8 minutes ago" by hand.
- [x] The three binaries take **no device class** — none fits, and the translated names carry the meaning. They are the automation *conditions* where the timestamps are the *triggers*.
- [x] The six totals declare their reset at the Household's Day Start instant from the payload. A sensor must **never** re-derive "today" from local midnight.
- [x] Two entities on the Household device: a **diagnostic** last-update timestamp (the coordinator's own "when did I last hear the server" — the staleness tell availability cannot express), and a **caregiving** binary sensor.
- [x] Entities **exist with state unknown** when inapplicable — a cleared Target must never break a family's dashboard. The exception is the appear-on-first-use pair, created from what the payload carries and **never removed once created**.
- [x] Names translated in **en, de and ro** from the table in spec §6.8 — never hardcoded English. The Romanian cells marked in that table ship as coined; the native pass is a pre-1.0.0 item.
- [x] A line under `## [Unreleased]` in `CHANGELOG.md`, same commit.

## Comments

**Built.** `entity.py`, `sensor.py`, `binary_sensor.py`; `tests/test_entities.py`.

Two notes:

- **`entity.py` is a fourth module** the spec's layout sketch does not list. It
  holds the two device shapes and `async_add_baby_entities()`, which is where both
  existence rules live — dynamic devices and appear-on-first-use — and having them
  in one place is what keeps the three platforms from each growing their own.
- **Device identifiers are prefixed** `baby_<id>` and `household_<id>`, so the two
  services can tell a Baby's device from the Household's. Entity `unique_id`s are
  untouched: `{baby_id}_{key}` and `{household_id}_{key}`, byte-for-byte the
  payload's field names, as spec §6.5 fixes them.

**Review follow-up.** `async_remove_config_entry_device` was missing, so *and
removable* was not true — Home Assistant offers no delete button without it. A
Baby the payload has stopped carrying can now be removed by hand; one who is
still there cannot, because the device would come back on the next read, and the
Household's own device never can while the entry is loaded.
