# 05 — Six buttons and two services

**What to build:** The write surface — what a wall offers, and what a mis-press costs. Writes go down the one write path there is, as plain revisions with client-minted ids, so a retry after a lost response is a no-op.

Spec §6.6.

**Blocked by:** 04 — Sixteen entities stand for a Baby.

**Status:** ready-for-agent

- [ ] **Six buttons** on each Baby's device: sleep start and end, breast-feed start and end, tummy-time start and end. Breast is the only Feed startable without arguments.
- [ ] **Two services** for the argumented actions — a bottle feed and a nappy — both **targeting the Baby's device**. There is **never a raw baby id field in the call schema**; the integration resolves device to Baby.
- [ ] Services are registered so automations validate **even when no entry is loaded**.
- [ ] Service names, descriptions and field labels live in **translations**, not in the service descriptor file.
- [ ] Availability mirrors the app's own reflow — no sleep button while one runs, no end-tummy without a running stretch. **Convenience, not enforcement**: the server never assumes we filtered anything, and the races land on rules it already holds.
- [ ] **A mis-press waits for a phone.** A wall has no toast and no undo window; no delete surface is offered — deliberately absent, not forgotten.
- [ ] The outbox is **bounded at 50** queued revisions and **visible** as a diagnostic pending-writes sensor on the Household device. At the bound a press **raises an error in the UI** rather than queuing silently — a hub is not a phone, and silently queuing feeds for six hours is worse than saying it did not send.
- [ ] **No repair issue for a backlog.** A non-empty outbox is visible state, not a condition needing repair.
- [ ] A line under `## [Unreleased]` in `CHANGELOG.md`, same commit.
