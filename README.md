# Baby Log Book for Home Assistant

The Home Assistant integration for [Baby Log Book](https://github.com/derico-de/baby-log-book)
— a shared, offline-first log of a baby's day.

It puts a Household's babies on a wall panel: when the last feed was, whether a
nap is running, how much milk went in today — and six buttons plus two actions
for the things a passing parent wants to log without unlocking a phone.

The integration talks to *your* deployment. There is no cloud in the middle: you
self-host Baby Log Book, paste a Claim Link into the config flow, and Home
Assistant becomes a **Hub** — a Device with its own Caregiver Member in the
Household, visible and revocable in the app's members list like any other.

## Status

**Not built yet.** The specification is being written in the sibling repo, at
`../baby-log-book/.scratch/home-assistant/`. This repository exists so the work
has a home before it starts.

## Install

Once released: HACS → Integrations → the three-dot menu → *Custom repositories*
→ this repo, category *Integration*. Then *Add integration* → **Baby Log Book**
and paste a Claim Link from the app's Settings.

## Compatibility

Each release names the oldest server and the oldest Home Assistant it works
with. The table lands here with the first release.

| Integration | Needs Baby Log Book | Needs Home Assistant |
| --- | --- | --- |
| _unreleased_ | — | — |

## Licence

AGPL-3.0-or-later, the same as the server. See [LICENSE](LICENSE).
