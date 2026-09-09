# 03 — The coordinator keeps a live picture

**What to build:** One coordinator holding the Household's current state, woken by the server's existing event stream and falling back to polling when that is down. The cadence numbers are **contract**, not suggestions — implement them rather than inventing them.

Spec §6.4, plus the setup-and-runtime half of §6.3.

**Blocked by:** 02 — A pasted Claim Link sets up the integration.

**Status:** ready-for-agent

- [ ] A `DataUpdateCoordinator` subclass with the config entry passed **explicitly** to the constructor.
- [ ] The event stream is the wake signal; a wake triggers a **conditional** state read, so a wake caused by our own write costs a not-modified. Wakes debounce at about a second.
- [ ] Poll floor **5 minutes** while the stream is healthy; **60 seconds** while it is down — the wall is the Household's live surface and five stale minutes during an outage would be noticed.
- [ ] Stream reconnect: exponential backoff, **base 5 s, cap 5 min, full jitter**. A deploy must not bring the fleet back in one second.
- [ ] The last ETag is echoed **verbatim** and **never parsed** — the format is the server's freedom. A not-modified response keeps the previous data and counts as a successful update.
- [ ] The clock offset is recomputed from the server's time on **every** non-304 response and applied to every merge key we mint.
- [ ] Network failure at setup uses the framework's own not-ready retry — **never a hand-written setup retry loop**. Runtime failures mark entities unavailable, keep the cadence, and log **once per outage** and once on recovery.
- [ ] A line under `## [Unreleased]` in `CHANGELOG.md`, same commit.
