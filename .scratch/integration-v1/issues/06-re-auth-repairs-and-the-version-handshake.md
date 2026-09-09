# 06 — Re-auth, repairs and the version handshake

**What to build:** What happens when the panel loses its footing — signed out, removed, hosting paused, or talking to a server that is the wrong age. Each lands on exactly one idiom, and there are exactly three repair issues.

Spec §6.3 (the runtime rows), §6.7 (the three repairs) and §7.1 (the handshake).

**Blocked by:** 03 — The coordinator keeps a live picture.

**Status:** ready-for-agent

- [ ] A stale session opens **re-auth**, which asks for a **Rescue Link** a Parent mints from Settings — reusing the setup flow's one field and its error rows.
- [ ] A claim during re-auth that yields a **different Member** aborts, after first discarding the mis-claimed session — the link is spent, because the preview is deliberately thin, but nothing stays bound wrong.
- [ ] **Removed never opens re-auth.** A re-auth dialog would ask for a Rescue Link that cannot exist, because Removal burns them. Instead: a non-fixable **error** repair issue, stop the stream, stop polling, entities unavailable. Reconnecting is a new Invite and a **new entry**.
- [ ] **Hosting paused** raises a non-fixable **warning** repair issue — a billing state, not a defect — marks entities honestly unavailable, drops the stream, and polls at the **5-minute floor**, not the outage cadence. Nothing changes while paused. The first good response deletes the issue and restores normal cadence; reactivation stays anticlimactic.
- [ ] The same two conditions at **setup** are permanent errors rather than retries.
- [ ] The version handshake gates on the server's **release number** against a baked-in minimum, with the concrete numbers in the message. Server too old: a claim-time form error **and** a setup error. This integration too old: the third repair issue.
- [ ] **No per-response version check** — a server rolled back mid-flight is an operator act, out of contract, and surfaces at the next reload. That check would be the fourth idiom this taxonomy exists to prevent.
- [ ] A line under `## [Unreleased]` in `CHANGELOG.md`, same commit.
