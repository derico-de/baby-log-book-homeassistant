# 02 — A pasted Claim Link sets up the integration

**What to build:** The way in. A Parent sends a Claim Link over WhatsApp; the user pastes the whole URL into one field and the panel is bound to the Household. Every way that can fail maps to **exactly one** Home Assistant idiom — the table exists so nobody invents a fourth.

Spec §6.2 and the claim-time half of §6.3, which is a table to implement row by row.

**Blocked by:** 01 — The repo builds, lints and validates green.

**Status:** resolved

- [x] **One form field**: the pasted Claim Link URL, exactly what Settings mints. The flow parses origin and token from it; nothing else is asked.
- [x] Preview first — **looking never spends the link** — then claim on confirm.
- [x] **Every pre-claim failure is a form error** so the user re-pastes. Aborts are reserved for identity outcomes.
- [x] All eleven rows of the claim-time table, each on its own key, each translated.
- [x] Plain `http://` is refused **against public hosts only** — loopback, RFC1918, `.local` and `.internal` stay exempt, so self-hosters and the dev env are unblocked. The flow checks, because the server cannot reliably see its own scheme behind a proxy.
- [x] Config entry `unique_id` = the **Household id**; a second wall panel is a second HA instance, not a second entry. The claimed Member id lives on the entry.
- [x] **Both kinds of link are accepted** at initial setup — an Invite for a Hub creates the Member, a Rescue Link re-binds one. Kind is never enforced; identity is.
- [x] Credentials live on the config entry, as Home Assistant stores every credential.
- [x] A line under `## [Unreleased]` in `CHANGELOG.md`, same commit.

## Comments

**Built.** `config_flow.py`, with every row of the claim-time table in
`tests/test_config_flow.py`.

Four notes, one of them a wire change:

- **The preview now carries the version block** — a server-half change that
  landed first, backward-compatibly, as `AGENTS.md` requires
  (`src/routes/api/claim/+server.ts`). Without it the flow had no release number
  before the link was spent, and spec §6.3's `server_too_old` **form error** was
  not implementable: only the claim's answer carried one. Folded into spec §6.2.
- **The preview parameter is `t`, not `token`** — the spec §6.2 prose said
  `?token=`; `claimUrl()` in `claims.ts` has always minted `?t=`. Corrected in the
  spec; the implementation was right.
- **`already_configured` is only knowable after the claim.** The preview is
  deliberately thin and names no Household, so `_abort_if_unique_id_configured()`
  runs on the claim's answer. Pasting a second Invite for a Household already on
  this Home Assistant therefore spends it and creates a Member the abort then
  leaves stranded. Cheap to fix on the server (a Household id on the preview);
  not fixed here, because the spec calls the preview's thinness deliberate and
  this is the rare case rather than the ordinary one.
- **A single-label host is treated as private**, beside loopback, RFC1918,
  `.local` and `.internal`. `http://nas:5173` and `http://planetmobile:5173` are
  what a home network actually calls its machines, and a name with no dot cannot
  be a public DNS name.

**Review follow-up.** Two more hosts are exempt from the HTTPS rule: `.localhost`
(loopback by RFC 6761 — leaving it out was an oversight) and any **single-label**
host, which cannot be a public DNS name and is what a home network calls its
machines. Both folded into spec §6.3 with the reasoning.
