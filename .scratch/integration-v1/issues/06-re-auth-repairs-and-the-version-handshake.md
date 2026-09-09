# 06 — Re-auth, repairs and the version handshake

**What to build:** What happens when the panel loses its footing — signed out, removed, hosting paused, or talking to a server that is the wrong age. Each lands on exactly one idiom, and there are exactly three repair issues.

Spec §6.3 (the runtime rows), §6.7 (the three repairs) and §7.1 (the handshake).

**Blocked by:** 03 — The coordinator keeps a live picture.

**Status:** resolved

- [x] A stale session opens **re-auth**, which asks for a **Rescue Link** a Parent mints from Settings — reusing the setup flow's one field and its error rows.
- [x] A claim during re-auth that yields a **different Member** aborts, after first discarding the mis-claimed session — the link is spent, because the preview is deliberately thin, but nothing stays bound wrong.
- [x] **Removed never opens re-auth.** A re-auth dialog would ask for a Rescue Link that cannot exist, because Removal burns them. Instead: a non-fixable **error** repair issue, stop the stream, stop polling, entities unavailable. Reconnecting is a new Invite and a **new entry**.
- [x] **Hosting paused** raises a non-fixable **warning** repair issue — a billing state, not a defect — marks entities honestly unavailable, drops the stream, and polls at the **5-minute floor**, not the outage cadence. Nothing changes while paused. The first good response deletes the issue and restores normal cadence; reactivation stays anticlimactic.
- [x] The same two conditions at **setup** are permanent errors rather than retries.
- [x] The version handshake gates on the server's **release number** against a baked-in minimum, with the concrete numbers in the message. Server too old: a claim-time form error **and** a setup error. This integration too old: the third repair issue.
- [x] **No per-response version check** — a server rolled back mid-flight is an operator act, out of contract, and surfaces at the next reload. That check would be the fourth idiom this taxonomy exists to prevent.
- [x] A line under `## [Unreleased]` in `CHANGELOG.md`, same commit.

## Comments

**Built.** The taxonomy across `coordinator.py` and `config_flow.py`, the three
issues in `issues.py`; covered in `tests/test_coordinator.py`.

Two notes:

- **The module is `issues.py`, not `repairs.py`.** Home Assistant treats a
  `repairs` module as a *platform* and logs an error for one that does not export
  `async_create_fix_flow`. All three issues are non-fixable by design, so there is
  no fix flow to export, and naming the module after a platform we deliberately do
  not implement would have bought a permanent error line in every log.
- **The "integration too old" issue needed a concrete trigger.** ADR-0039 says
  *when the integration recognizes an incompatible response*; the implementation
  is `IncompatibleResponse`, raised when a `200` from the state read carries no
  readable Household. It is the narrowest honest reading, and it is rare by
  construction because the ordering rule puts the server first.
- **The issue ids carry the config entry id** (`hosting_paused_<entry_id>`), so a
  Home Assistant watching two Households does not overwrite one issue with the
  other. Still three *kinds*, and the translation key is the bare name.

**Review follow-up.** The reason `repairs.py` is `issues.py` is sharper than
first written: Home Assistant does not merely log — `_process_repairs_platform`
(`homeassistant/components/repairs/issue_handler.py`) **raises**
`HomeAssistantError("Invalid repairs platform")` for a `repairs` module with no
`async_create_fix_flow`. All three issues are non-fixable by design, so there is
none to export.
