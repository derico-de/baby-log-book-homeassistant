# 03 — The coordinator keeps a live picture

**What to build:** One coordinator holding the Household's current state, woken by the server's existing event stream and falling back to polling when that is down. The cadence numbers are **contract**, not suggestions — implement them rather than inventing them.

Spec §6.4, plus the setup-and-runtime half of §6.3.

**Blocked by:** 02 — A pasted Claim Link sets up the integration.

**Status:** resolved

- [x] A `DataUpdateCoordinator` subclass with the config entry passed **explicitly** to the constructor.
- [x] The event stream is the wake signal; a wake triggers a **conditional** state read, so a wake caused by our own write costs a not-modified. Wakes debounce at about a second.
- [x] Poll floor **5 minutes** while the stream is healthy; **60 seconds** while it is down — the wall is the Household's live surface and five stale minutes during an outage would be noticed.
- [x] Stream reconnect: exponential backoff, **base 5 s, cap 5 min, full jitter**. A deploy must not bring the fleet back in one second.
- [x] The last ETag is echoed **verbatim** and **never parsed** — the format is the server's freedom. A not-modified response keeps the previous data and counts as a successful update.
- [x] The clock offset is recomputed from the server's time on **every** non-304 response and applied to every merge key we mint.
- [x] Network failure at setup uses the framework's own not-ready retry — **never a hand-written setup retry loop**. Runtime failures mark entities unavailable, keep the cadence, and log **once per outage** and once on recovery.
- [x] A line under `## [Unreleased]` in `CHANGELOG.md`, same commit.

## Comments

**Built.** `coordinator.py` and the client in `api.py`; cadence and backoff
covered in `tests/test_coordinator.py`.

Two notes:

- **The stream's `hello` event is the "listener connected" signal.** The server
  sends `event: hello` as soon as the connection is up (`src/routes/api/sync/live/+server.ts`),
  so `async_events()` yields event *names* and the coordinator relaxes to the
  five-minute floor on `hello` rather than waiting for the first wake. Without it
  a quiet Household would poll at the outage cadence for ever.
- **The stream stops itself on `403` and `402`**, because it 403s and 402s too.
  An `asyncio.Event` gates the reconnect loop; leaving Lapsed sets it again, and
  removal clears it for good.
