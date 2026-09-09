# 08 — Both halves talked to each other

**What to build:** The first time the two halves meet. Everything up to here was built against a mocked server; this ticket puts a real integration in front of a real deployment on the dev-env Home Assistant container and watches it work.

Deliberately **not** CI. The integration's own suite stays hermetic — no live instance, ever — and the container stays a human-eyeball surface, as spec §6.9 says.

**Blocked by:** every ticket in this repo, and in the server repo: *The derived read*, *A Member is marked as a person's or a Hub's*, *A Rescue Link minted from Settings*, and *The Lapsed gate*.

**Status:** resolved

- [x] A Parent mints an Invite **for a Hub** in Settings; the config flow claims it; the entry appears bound to the Household.
- [x] The members list shows the new Member marked as a Hub, in the Caregiver role, and offers no way to promote it.
- [x] Devices appear per Baby with their sixteen entities, plus the Household device with its two. Timestamps render relative **in German** on a wall-panel dashboard.
- [x] A Household that has never logged tummy time or a bottle shows neither of those totals; logging one on a phone makes the entity appear, and it never disappears again.
- [x] Pressing a button writes an Entry that shows up on a phone's timeline, attributed to the Hub's Member.
- [x] A quiet minute produces not-modified responses; a write produces exactly one wake and one fetch.
- [x] Removing the Hub's Member stops the panel and raises the removed repair issue; the panel does **not** offer re-auth.
- [x] A Rescue Link minted from Settings re-binds the panel through the re-auth flow, and the phone stays signed in.
- [x] Findings recorded on this ticket. Anything the spec got wrong is corrected **in the spec**, not just in code.

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

**Done.** A real integration, in the dev-env Home Assistant container, in front of
a real deployment — a throwaway one on its own `DATA_DIR`, never the household in
the dev container, which is somebody's. A Parent called Sofia, a Baby called Emma,
and a second Baby called Noah added later from the phone to see her arrive.

Every box above is ticked, and four of them only after a fix. What the mocked
suite could not have caught:

### The one that mattered: a Removal answered `401`, not `403`

Removing the Hub's Member put the panel into **re-auth** — the dialog spec §6.3
says must never open, because it asks for a Rescue Link that Removal has already
burnt. A dead end, in the one place the design promised there would not be one.

`revokeMember` does two things: it marks the Member and it kills every token they
had. `resolveSession` asked about the token first, so `removed` was unreachable by
the only path that produces it, and every removed Device heard `unauthenticated`
instead. The unit test for the `403` set `removed_at` by hand and never revoked, so
it passed against a state the app cannot actually reach.

It was worse than a wrong word for a phone. `401` deliberately never wipes local
data — only `removed` does (`sync.ts`, `wipeEverything`) — so removing a Caregiver
left the Household's whole log sitting on their phone. The blast radius of a
Removal was smaller than every screen that offers one says it is. Both halves of
that chain were already tested (`replica.test.ts`: *never wipes on a 401*, *wipes
on a removed response*); what nothing tested was whether the server ever said
`removed` to a Device it had just revoked. Now something does.

Fixed server-side in `resolveSession`: removal is asked before revocation, with a
test that does both halves of a removal — mark the Member *and* `revokeMember` —
rather than only the half the old one did. With it, the panel does exactly what the
row says — repair issue `member_removed`, severity error, no re-auth, polling
stopped — and it hears about it through the event stream in about ten seconds
rather than waiting for a poll.

### A Household with no name arrives as a blank

Naming a Household is optional in the app and nothing in the app displays the name,
so plenty of them never get one. Home Assistant has no such freedom: the entry was
titled `""`, the Household device was nameless, and its three entities became
`binary_sensor.betreuung` rather than `binary_sensor.<household>_caregiving`. The
`member_removed` repair read *…for* and then stopped.

`DEFAULT_HOUSEHOLD_NAME = "Baby Log Book"`, applied where a name is shown — the
entry title, the device, the repair placeholders — and not to the stored
`household_name`, which stays the blank the server sent.

### A Rescue Link previews without a name

The confirm step reads *Server: …* / *For: {name}*, and a rescue link's preview
carries no `display_name` — deliberately, because an unauthenticated look must not
be a name oracle. So re-auth confirmed against *For:* and nothing. A founding link
previews the same way.

Now two step ids over the one code path, the way `user` and `reauth_confirm`
already are: `confirm` when the link names somebody, `confirm_unnamed` when it does
not, in en, de and ro. A translation cannot leave a line out, so the wording has to.

### The removed repair issue outlived its entry

`member_removed` is persistent on purpose — nothing about a Removal heals — and the
README's own instruction is to delete the entry and add the integration again.
Doing exactly that left a red, unfixable card about a Household this Home Assistant
no longer had, and no way to dismiss it. `async_remove_entry` now takes all three
issues down with the entry.

### The README oversold one word

*"A button is hidden where the app would hide it"* — it goes **unavailable**, which
Home Assistant greys out and labels *Nicht verfügbar*. The spec had it right
(§6.6 says `unavailable`); only the README was wrong. Corrected, with the
`visibility` condition named for anybody who wants the tile gone too.

## What held, exactly as written

- **The cadence numbers are real** — better than the box above them says. A quiet
  minute with the stream up costs **nothing at all**, not even a not-modified: the
  poll is a five-minute safety net, so a not-modified is what a quiet *five*
  minutes costs, and it lands on the second and answers `304`. One button press
  costs one `POST /api/sync/push` and one conditional `GET /api/hub/state` about a
  second later: one wake, one fetch, and the debounce visible in the gap.
- **The whole error taxonomy**, against real HTTP rather than a mock: a deployment
  running 1.19.3 gives `server_too_old` naming **both** numbers, something that is
  not us gives `not_baby_log_book`, a paused Household gives `hosting_paused`, a
  spent link gives `link_used`, a dead port gives `cannot_connect`, a public
  `http://` origin gives `http_public_origin`, and rubbish gives `link_unknown`.
  Looking never spent the link — the app still listed it as waiting afterwards.
- **The version block on the claim preview** (spec §6.2) is there and is what the
  gate reads.
- **The three `*_entry_id` fields** (spec §5.5) do their job across the halves: a
  Sleep started on the phone was ended by the panel's *Sie ist wach*, and the
  timeline reads `Sofia · nap · edited by Home Assistant`.
- **Hub-ness, end to end.** Ticking *this one is for a Hub* disables the role
  select at caregiver; the members list reads `Home Assistant · Hub · caregiver`
  and offers Sign-in link and Remove and no way to promote.
- **Appear-on-first-use is a Household rule, not a Baby's** — the server omits
  `milk_today`/`tummy_today` until the Household has ever logged one. Neither
  existed until the bottle; both then existed for Noah the moment he was added,
  which is the rule working, not a leak.
- **A Baby added on a phone arrives** — Noah's 22 entities within a wake, no
  re-adding.
- **Both actions** — `log_bottle_feed` and `log_nappy` — write through a device
  target with no Baby id anywhere.
- **German renders itself.** *Vor 27 Minuten*, *In 3 Stunden*, *In 48 Minuten*, on
  stock tile cards, with nothing ticking.
- **The phone stayed signed in** through the Hub's sign-out, its Rescue Link and
  its Removal. Sofia's session was never touched.

### The Household device has three entities, not two

Spec §6.5 said **two** and listed `last_update` and `caregiving`; `pending_writes`
was decided in §6.6 and never folded into the count, and the box above inherited
the mistake. Corrected in the spec, in both places it was stated.

## Smaller notes, left alone

- The first poll after a setup or a reload lands at the 60-second cadence rather
  than five minutes: Home Assistant arms the timer when the first entity is added
  and `hello` arrives too late to re-arm it. It costs one `304` per load, which is
  cheap enough to leave — noted in spec §6.4 so the next reader is not surprised
  by a number the table does not predict.
- The name fallback is applied where a name is *shown*, so an entry claimed before
  it existed would keep its blank title. Nothing has shipped — `manifest.json` is
  still `0.0.0` — so there is no such entry anywhere but this dev instance, and a
  migration for a population of zero is not worth the code.
- Long compound names truncate on tile cards — *Emma Wachfenster vor…* — as the
  README already says. The `Baby Log Book` fallback makes the Household's own
  tiles worse; overriding `name:` on the card is the answer either way.
- The entity ids a Household gets are the ones it had when it was first seen, so
  naming a Household later does not rename them. That is Home Assistant's rule,
  not ours.

## What the dev environment needed

Both in the server repo, and both deliberate:

- **The recorder's SQLite cannot live on the bind-mounted `/config`.** It declared
  itself corrupt every three seconds and left a renamed copy behind — 117 of them
  by the time it was noticed, and `history`, `logbook` and `energy` all failed to
  set up. `recorder.db_url` now points inside the container. (`mypy` hits the same
  wall on this filesystem: `--cache-dir` off the workspace.)
- **The mocked template entities are gone from `configuration.yaml`.** They had
  claimed the entity ids the real integration wanted, which sent every real one to
  a `_2` suffix; they were removed from the registry too. Their own comment said
  the real integration replaces all of this, and now it has.

The integration is installed at `ha/config/custom_components/baby_log_book`, which
is gitignored runtime state: copy it in again after a change and restart the
container.
