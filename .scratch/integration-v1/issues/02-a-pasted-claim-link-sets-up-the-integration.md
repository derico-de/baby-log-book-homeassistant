# 02 — A pasted Claim Link sets up the integration

**What to build:** The way in. A Parent sends a Claim Link over WhatsApp; the user pastes the whole URL into one field and the panel is bound to the Household. Every way that can fail maps to **exactly one** Home Assistant idiom — the table exists so nobody invents a fourth.

Spec §6.2 and the claim-time half of §6.3, which is a table to implement row by row.

**Blocked by:** 01 — The repo builds, lints and validates green.

**Status:** ready-for-agent

- [ ] **One form field**: the pasted Claim Link URL, exactly what Settings mints. The flow parses origin and token from it; nothing else is asked.
- [ ] Preview first — **looking never spends the link** — then claim on confirm.
- [ ] **Every pre-claim failure is a form error** so the user re-pastes. Aborts are reserved for identity outcomes.
- [ ] All eleven rows of the claim-time table, each on its own key, each translated.
- [ ] Plain `http://` is refused **against public hosts only** — loopback, RFC1918, `.local` and `.internal` stay exempt, so self-hosters and the dev env are unblocked. The flow checks, because the server cannot reliably see its own scheme behind a proxy.
- [ ] Config entry `unique_id` = the **Household id**; a second wall panel is a second HA instance, not a second entry. The claimed Member id lives on the entry.
- [ ] **Both kinds of link are accepted** at initial setup — an Invite for a Hub creates the Member, a Rescue Link re-binds one. Kind is never enforced; identity is.
- [ ] Credentials live on the config entry, as Home Assistant stores every credential.
- [ ] A line under `## [Unreleased]` in `CHANGELOG.md`, same commit.
