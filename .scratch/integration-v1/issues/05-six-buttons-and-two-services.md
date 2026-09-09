# 05 — Six buttons and two services

**What to build:** The write surface — what a wall offers, and what a mis-press costs. Writes go down the one write path there is, as plain revisions with client-minted ids, so a retry after a lost response is a no-op.

Spec §6.6.

**Blocked by:** 04 — Sixteen entities stand for a Baby.

**Status:** resolved

- [x] **Six buttons** on each Baby's device: sleep start and end, breast-feed start and end, tummy-time start and end. Breast is the only Feed startable without arguments.
- [x] **Two services** for the argumented actions — a bottle feed and a nappy — both **targeting the Baby's device**. There is **never a raw baby id field in the call schema**; the integration resolves device to Baby.
- [x] Services are registered so automations validate **even when no entry is loaded**.
- [x] Service names, descriptions and field labels live in **translations**, not in the service descriptor file.
- [x] Availability mirrors the app's own reflow — no sleep button while one runs, no end-tummy without a running stretch. **Convenience, not enforcement**: the server never assumes we filtered anything, and the races land on rules it already holds.
- [x] **A mis-press waits for a phone.** A wall has no toast and no undo window; no delete surface is offered — deliberately absent, not forgotten.
- [x] The outbox is **bounded at 50** queued revisions and **visible** as a diagnostic pending-writes sensor on the Household device. At the bound a press **raises an error in the UI** rather than queuing silently — a hub is not a phone, and silently queuing feeds for six hours is worse than saying it did not send.
- [x] **No repair issue for a backlog.** A non-empty outbox is visible state, not a condition needing repair.
- [x] A line under `## [Unreleased]` in `CHANGELOG.md`, same commit.

## Comments

**Built.** `button.py`, the two services in `__init__.py`, the outbox on the
coordinator; `tests/test_actions.py`.

One wire change, and one note:

- **The payload now names the three running sessions** — `sleep_entry_id`,
  `feed_entry_id`, `tummy_entry_id`, added server-side first and folded into spec
  §5.5 and §6.6 with the reasoning. Three of the six buttons write `ended_at`, a
  revision addresses its entity **by id**, and the payload carried none: without
  this the panel could only end what it had started itself, so a Sleep begun on a
  phone could never be stopped at the wall — and *she's awake* is the button a
  passing parent presses most. Nothing closed, deleted or historical is named.
- **A write the server explicitly rejects is dropped, not retried.** A lost
  response is retried for ever, as the outbox is for; a `rejected` entry never
  becomes acceptable, and retrying it would block the fifty behind it.

**Review follow-up.** The outbox now lets go of **exactly what the server
settled**. `async_push` returns the accepted and rejected ids rather than raising
on a rejection, and anything the answer did not account for stays queued for the
next try. The old code dropped the whole batch on any rejection, which happened
to be safe — `push()` accounts for every revision it is given — but only by
accident, and it read as though it discarded siblings. A batch the server refuses
outright (a `400`) is still let go: that is not a thing a later attempt fixes.

Two smaller things: `MAX_VOLUME_ML` is **5000**, the server's own bound
(`entries.ts`), not the 2000 first written here — a client schema that disagrees
with the validator behind it is worse than no schema. And the two services'
*names* now read *pee & poop* rather than *nappy*, per `CONTEXT.md` (*Avoid:
Nappy and Diaper — both name the receptacle, and both go wrong at potty
training*). The service **id** stays `log_nappy`: spec §6.6 fixes it and
automations couple to it. The `where` option keeps *Nappy*, where the receptacle
is exactly what is meant.
