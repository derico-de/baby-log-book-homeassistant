# Changelog

All notable changes to the Baby Log Book integration for Home Assistant are
recorded here, newest first.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Every change lands under **Unreleased** when it is made; a release renames that
section to its version number, and `release.yml` publishes that section as the
GitHub release notes — which is what HACS shows to anybody considering the
update.

Versions are independent of the server's, from `1.0.0`. `manifest.json →
version` = the git tag = the GitHub release, bumped together in one commit.

## [Unreleased]

## [1.0.1] - 2026-09-10

### Fixed

- The server floor is `1.26.0`, the release that actually carries the wire this
  panel reads. `MIN_SERVER_VERSION` said `1.25.0` and no 1.25.0 deployment has
  ever had `GET /api/hub/state` — it shipped in 1.26.0, together with the Hub's
  Member kind, the version a claim link reports before it is spent, and the
  running sessions the three end-buttons need. The old number let a 1.25.0
  server through setup, spent the one-shot Claim Link on it and then found
  nothing to read; the version gate now refuses it while the link is still
  good, which is the whole point of reading the version first (ADR-0039). The
  compatibility table in the README names the corrected floor for both
  releases.

## [1.0.0] - 2026-09-10

### Added

- The repo builds, lints and validates green: `pyproject.toml` under `uv`, ruff,
  mypy in strict mode and `pytest-homeassistant-custom-component` against one
  pinned Home Assistant, which is also the floor we claim. Two workflows — `ci.yml`
  on push, pull request and a weekly cron, with lint, test at a 95 % coverage
  floor and hassfest plus the HACS action; and `release.yml`, which **refuses** a
  tag whose number the manifest does not agree with and publishes this file's
  section for that version as the release notes. Dependabot weekly on both
  ecosystems.

- A pasted Claim Link sets up the integration. One field, the whole URL exactly
  as it arrived in the messenger; the flow reads the address and the token out
  of it, looks the link up without spending it, says what it found, and claims
  on confirm. Every way that can fail is a form error you re-paste into rather
  than a dead end — an expired link, one somebody already claimed, one that was
  revoked, an address that cannot be reached or does not answer like a Baby Log
  Book, hosting that is paused, a deployment too old for this panel. Plain
  `http://` is refused against public addresses only, so a self-hosted server on
  a home network is never blocked. The Household is the identity: a second wall
  panel is a second Home Assistant, not a second entry. An invite for a hub and a
  sign-in link are both accepted.

- The coordinator keeps a live picture. The server's existing event stream is the
  wake-up signal and a poll is the fallback: a wake asks whether anything changed
  and costs nothing when it has not, the poll drops to a five-minute safety net
  while the stream is up and tightens to a minute while it is down, and a
  reconnect backs off from five seconds to five minutes with full jitter so a
  deploy does not bring every panel back in the same second. The panel's clock is
  corrected against the server's on every answer, so what it logs while cut off
  is dated the way a phone would date it.

- Sixteen entities stand for a Baby, on a device of her own, plus a device for the
  Household. Seven of them are instants — last feed, feed due, asleep since, awake
  since, wake window up, bottle life runs out, last poop — which Home Assistant
  renders as *12 minutes ago* and *in 3 hours*, live and in your language, with
  nothing ticking. Three are flags to write conditions against: asleep, feeding,
  bottle open. Six are today's totals, and they reset at the Household's own day
  start rather than at midnight. A baby added on a phone appears here without
  re-adding anything; a baby deleted on a phone leaves her device standing and
  removable rather than vanishing with her history; milk and tummy time appear
  the first time either is ever logged and never go away again; anything that
  does not apply reads as unknown rather than breaking a dashboard. The Household device carries when the panel
  last heard the server, and whether caregiving is switched on. Names in English,
  German and Romanian, in the app's own words.

- Six buttons and two actions. On each Baby: sleep and she's awake, feed and end
  feed, tummy time and off her tummy — and the three that end something end the
  one that is running, whoever started it, phone or panel. A bottle, and pee & poop,
  take arguments, so they are actions an automation or a script calls, aimed at
  the Baby's device; there is no baby id to type anywhere. A button is only
  offered where the app would offer it, which is a convenience and not a rule —
  the rules are the server's. Presses queue if the server is out and go when it
  is back — and the queue lets go of exactly what the server said it had taken,
  so nothing is silently dropped and nothing is retried for ever. It is visible
  on the Household device and bounded at fifty, and at the bound a press says
  plainly that it did not send rather than swallowing it. A mis-press waits for
  a phone: a wall has no undo.

- Re-auth, repairs and the version handshake. A panel that has been signed out
  asks for a sign-in link a parent mints in Settings — the same words as a lost
  phone — and a link that turns out to bind somebody else is discarded rather
  than left bound wrong. A panel whose member has been removed does **not** ask
  to sign in again, because removal burns the links it would ask for: it stops,
  says so as a repair issue, and reconnecting means a fresh invite and a fresh
  entry. Paused hosting is a warning rather than a fault, polls gently and clears
  itself the moment hosting resumes. There are exactly three repair issues and
  never a fourth.

- The README a stranger follows: what this is, installing it, claiming a link,
  revoking it, signing back in, a dashboard card, two automations to copy, a
  one-press bottle script, what it deliberately does not do, and the
  compatibility table — with a screenshot of the one step that is done in the
  app rather than in Home Assistant, ticking *this is for a Hub* on the invite.

### Fixed

- `LICENSE` carries the licence. It held a maintainer's note where the verbatim
  GNU AGPL-3.0 text belongs — written on a machine that had no copy of it and no
  way to fetch one — and AGPL §14 wants the real thing before the program is
  conveyed to anybody. A release is exactly that moment.


- A Household that has never been named arrives with a name anyway. Naming one
  is optional in the app, and nothing in the app displays it, so plenty of them
  never get one — but Home Assistant writes it on the entry, on a device and
  into three entity ids, and a blank there reads as a bug. Unnamed Households are
  **Baby Log Book** on this side. What the server sent is kept as it was; only
  what is shown falls back.

- A sign-in link is confirmed in its own words. The preview a Claim Link gives is
  deliberately thin and a sign-in link carries no name at all, so the confirmation
  read *For:* and then stopped. It now has a second wording, in all three
  languages, for a link that names nobody — which is a sign-in link and a founding
  link both.

- Deleting the entry takes its repair issues with it. The removed-Member issue is
  persistent on purpose, because nothing about a Removal heals; the way back from
  one is to delete the entry and add the integration again, which left a red card
  standing about a Household that was no longer there — and not a fixable one, so
  nobody could dismiss it either.

- The README said a button is *hidden* where the app would hide it. It goes
  unavailable, which Home Assistant greys out and labels; the `visibility`
  condition that does hide the tile is named for anybody who wants that.
