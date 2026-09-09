# 08 — Both halves talked to each other

**What to build:** The first time the two halves meet. Everything up to here was built against a mocked server; this ticket puts a real integration in front of a real deployment on the dev-env Home Assistant container and watches it work.

Deliberately **not** CI. The integration's own suite stays hermetic — no live instance, ever — and the container stays a human-eyeball surface, as spec §6.9 says.

**Blocked by:** every ticket in this repo, and in the server repo: *The derived read*, *A Member is marked as a person's or a Hub's*, *A Rescue Link minted from Settings*, and *The Lapsed gate*.

**Status:** ready-for-human

- [ ] A Parent mints an Invite **for a Hub** in Settings; the config flow claims it; the entry appears bound to the Household.
- [ ] The members list shows the new Member marked as a Hub, in the Caregiver role, and offers no way to promote it.
- [ ] Devices appear per Baby with their sixteen entities, plus the Household device with its two. Timestamps render relative **in German** on a wall-panel dashboard.
- [ ] A Household that has never logged tummy time or a bottle shows neither of those totals; logging one on a phone makes the entity appear, and it never disappears again.
- [ ] Pressing a button writes an Entry that shows up on a phone's timeline, attributed to the Hub's Member.
- [ ] A quiet minute produces not-modified responses; a write produces exactly one wake and one fetch.
- [ ] Removing the Hub's Member stops the panel and raises the removed repair issue; the panel does **not** offer re-auth.
- [ ] A Rescue Link minted from Settings re-binds the panel through the re-auth flow, and the phone stays signed in.
- [ ] Findings recorded on this ticket. Anything the spec got wrong is corrected **in the spec**, not just in code.

## Comments

**Unblocked.** Every ticket in this repo is resolved, and so is every server-half
ticket it named. The suite is hermetic and green (108 tests, 99 % coverage), ruff
and mypy are clean, and the integration has never yet met a running deployment —
which is exactly what this ticket is for.

Two things to look at first, because they are the parts the mocked suite cannot
prove and the build changed:

- **The three `*_entry_id` fields**, added to `GET /api/hub/state` for this build
  (spec §5.5). Start a Sleep on a phone and press *she's awake* on the panel.
- **The version block on the claim preview**, added so the config flow can gate on
  the server's release before the link is spent (spec §6.2). Point the flow at a
  deployment and check the form error names both numbers.
