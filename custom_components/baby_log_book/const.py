"""Constants for the Baby Log Book integration.

The cadence numbers below are **contract**, not tuning knobs: they were decided
in the specification (§6.4) against what a wall panel is for, and a Household
that changes them changes what the wall is. The same goes for the outbox bound.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "baby_log_book"

#: The oldest Baby Log Book this release speaks to. Raised only by a release
#: whose code needs something newer, and only after that something has shipped
#: server-side (ADR-0039).
MIN_SERVER_VERSION: Final = "1.26.0"

#: The session cookie the server sets on a claim. Named here because the
#: integration holds the value itself rather than letting a cookie jar do it:
#: it survives a restart in the config entry, as Home Assistant stores every
#: credential.
SESSION_COOKIE: Final = "blb_session"

CONF_ORIGIN: Final = "origin"
CONF_SESSION: Final = "session"
CONF_MEMBER_ID: Final = "member_id"
CONF_HOUSEHOLD_ID: Final = "household_id"
CONF_HOUSEHOLD_NAME: Final = "household_name"
CONF_DEVICE_ID: Final = "device_id"
CONF_CLAIM_LINK: Final = "claim_link"

#: What the Household is called when it has not been named. The app leaves the
#: name optional — nothing in it displays one — but Home Assistant has to write
#: something on the entry, on the device and into three entity ids, and a blank
#: there reads as a bug rather than as a Household nobody bothered to name.
DEFAULT_HOUSEHOLD_NAME: Final = "Baby Log Book"

# --- cadence (spec §6.4) -------------------------------------------------

#: A burst of revisions is one refresh.
WAKE_DEBOUNCE_S: Final = 1.0
#: A safety net under a healthy stream; nearly always a not-modified.
POLL_STREAM_HEALTHY: Final = timedelta(minutes=5)
#: The wall is the Household's live surface, and five stale minutes during an
#: outage would be noticed.
POLL_STREAM_DOWN: Final = timedelta(seconds=60)
#: Nothing changes while hosting is paused.
POLL_LAPSED: Final = timedelta(minutes=5)
#: Exponential, full jitter. A deploy must not bring the fleet back in one
#: second.
BACKOFF_BASE_S: Final = 5.0
BACKOFF_CAP_S: Final = 300.0

#: A hub is not a phone: silently queuing feeds for six hours is worse than
#: saying it did not send.
OUTBOX_LIMIT: Final = 50

# --- repair issues (spec §6.7) — exactly three ---------------------------

ISSUE_MEMBER_REMOVED: Final = "member_removed"
ISSUE_HOSTING_PAUSED: Final = "hosting_paused"
ISSUE_INTEGRATION_OUTDATED: Final = "integration_outdated"

# --- the action surface (spec §6.6) --------------------------------------

SERVICE_LOG_BOTTLE_FEED: Final = "log_bottle_feed"
SERVICE_LOG_NAPPY: Final = "log_nappy"

ATTR_VOLUME_ML: Final = "volume_ml"
ATTR_CONTENTS: Final = "contents"
ATTR_LEFTOVER_ML: Final = "leftover_ml"
ATTR_PEE: Final = "pee"
ATTR_POOP: Final = "poop"
ATTR_WHERE: Final = "where"
ATTR_CONSISTENCY: Final = "consistency"

BOTTLE_CONTENTS: Final = ("breast_milk", "formula", "other")
NAPPY_WHERE: Final = ("nappy", "potty", "toilet")
NAPPY_CONSISTENCY: Final = ("soft", "firm", "runny", "hard")

#: The server's own bound on both millilitre fields (`MAX_VOLUME_ML`,
#: `entries.ts`), restated here because a `voluptuous` schema is what tells an
#: automation author they have typed something the push will refuse. Not a rule
#: of ours: if the server's moves, this follows it.
MAX_VOLUME_ML: Final = 5000

# --- entity keys ---------------------------------------------------------
# Byte-for-byte the payload's field names (spec §5.5, §6.5), so payload to
# entity needs no translation table. Renaming one is a wire change.

TIMESTAMP_KEYS: Final = (
    "last_feed",
    "feed_due",
    "asleep_since",
    "awake_since",
    "wake_window_up",
    "bottle_runs_out",
    "last_poop",
)
BINARY_KEYS: Final = ("asleep", "feeding", "bottle_open")
#: Always there, however quiet the day — zero is an answer.
TOTAL_KEYS: Final = ("feeds_today", "sleep_today", "pees_today", "poops_today")
#: Absent from the payload until the Household has **ever** logged one, created
#: on the first that arrives, and never removed again. The rule only adds.
FIRST_USE_TOTAL_KEYS: Final = ("milk_today", "tummy_today")

#: The Household device's own two, and its diagnostics. Neither has a payload
#: field behind it: they are what the coordinator knows about itself.
KEY_LAST_UPDATE: Final = "last_update"
KEY_PENDING_WRITES: Final = "pending_writes"
KEY_CAREGIVING: Final = "caregiving"
