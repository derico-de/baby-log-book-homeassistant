"""Exactly three repair issues, and never a fourth.

Repairs are reserved for the two version cases and the dead session. A backlog
in the outbox is **not** one of them: a non-empty outbox is visible state — the
``pending_writes`` sensor — not a condition anybody has to repair.

The issue ids carry the config entry id, because a Home Assistant watching two
Households has two of each; the *kinds* are still three, and the translation
key is the bare name.
"""

from __future__ import annotations

from typing import Final

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import (
    DOMAIN,
    ISSUE_HOSTING_PAUSED,
    ISSUE_INTEGRATION_OUTDATED,
    ISSUE_MEMBER_REMOVED,
    MIN_SERVER_VERSION,
)


def issue_id(kind: str, entry_id: str) -> str:
    """The id one Household's copy of an issue is filed under."""
    return f"{kind}_{entry_id}"


@callback
def async_member_removed(hass: HomeAssistant, entry_id: str, household: str) -> None:
    """The Member has been Removed, and there is no way back to this entry.

    Not fixable, and deliberately not a re-auth: a re-auth dialog would ask for
    a Rescue Link that cannot exist, because Removal burns them (ADR-0037).
    Reconnecting is a new Invite for a Hub and a **new** entry.
    """
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id(ISSUE_MEMBER_REMOVED, entry_id),
        is_fixable=False,
        is_persistent=True,
        severity=ir.IssueSeverity.ERROR,
        translation_key=ISSUE_MEMBER_REMOVED,
        translation_placeholders={"household": household},
    )


@callback
def async_hosting_paused(hass: HomeAssistant, entry_id: str, household: str) -> None:
    """A billing state, not a defect — so a warning, and nothing is fixable here."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id(ISSUE_HOSTING_PAUSED, entry_id),
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_HOSTING_PAUSED,
        translation_placeholders={"household": household},
    )


@callback
def async_integration_outdated(hass: HomeAssistant, entry_id: str) -> None:
    """The server said something this release cannot read (ADR-0039)."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id(ISSUE_INTEGRATION_OUTDATED, entry_id),
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_INTEGRATION_OUTDATED,
        translation_placeholders={"minimum": MIN_SERVER_VERSION},
    )


#: The three kinds, in one place. Anything that has to name all of them —
#: taking an entry's issues down with it — asks here rather than restating the
#: roster and letting the two lists drift.
KINDS: Final = (ISSUE_MEMBER_REMOVED, ISSUE_HOSTING_PAUSED, ISSUE_INTEGRATION_OUTDATED)


@callback
def async_clear(hass: HomeAssistant, kind: str, entry_id: str) -> None:
    """Take one down again. Idempotent, so nobody has to ask first."""
    ir.async_delete_issue(hass, DOMAIN, issue_id(kind, entry_id))


@callback
def async_clear_all(hass: HomeAssistant, entry_id: str) -> None:
    """Take all three down: what an entry raised, an entry takes with it."""
    for kind in KINDS:
        async_clear(hass, kind, entry_id)
