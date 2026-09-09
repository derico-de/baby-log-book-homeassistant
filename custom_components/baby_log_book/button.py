"""Six buttons per Baby — what a wall offers, and what a mis-press costs.

Availability mirrors the app's own reflow: no *Sleep* while one runs, no *Off
her tummy* without a running stretch. That is **convenience, not enforcement**.
The server never assumes the Hub filtered anything, and the race a stale read
lets through lands on rules the server already holds — two started Sleeps
reconcile through Session Merge, and a second Feed ends the first inside the
push transaction.

**A mis-press waits for a phone.** A wall has no toast and no undo window, and
no delete surface is offered here: deliberately absent, not forgotten.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BabyLogBookConfigEntry, BabyLogBookCoordinator
from .entity import BabyEntity, async_add_baby_entities

PARALLEL_UPDATES = 0

#: The side a wall's *Feed* button starts with. The phone owns `side`: choosing
#: it one-handed at a wall is fiddly, and the app's own default is the honest
#: thing for a button that takes no arguments.
DEFAULT_SIDE = "both"


@dataclass(frozen=True, kw_only=True)
class BabyButtonDescription(ButtonEntityDescription):
    """One button: when it is offered, and what it writes."""

    #: Whether the press makes sense given the last read.
    offered: Callable[[Mapping[str, Any]], bool]
    #: The running Entry this press ends, or `None` when it starts one.
    ends: str | None = None
    #: The Entry type this press starts, or `None` when it ends one.
    starts: str | None = None
    #: Payload fields beyond the shared creation ones.
    extra: Mapping[str, Any] | None = None


BUTTONS: tuple[BabyButtonDescription, ...] = (
    BabyButtonDescription(
        key="start_sleep",
        translation_key="start_sleep",
        starts="sleep",
        offered=lambda baby: not baby.get("asleep"),
    ),
    BabyButtonDescription(
        key="end_sleep",
        translation_key="end_sleep",
        ends="sleep_entry_id",
        offered=lambda baby: bool(baby.get("sleep_entry_id")),
    ),
    BabyButtonDescription(
        key="start_feed",
        translation_key="start_feed",
        starts="breast_feed",
        extra={"side": DEFAULT_SIDE},
        # A Feed while asleep keeps the Sleep running, so this one is never
        # withheld: the wall's start-feed never touches a Sleep.
        offered=lambda baby: True,
    ),
    BabyButtonDescription(
        key="end_feed",
        translation_key="end_feed",
        ends="feed_entry_id",
        offered=lambda baby: bool(baby.get("feed_entry_id")),
    ),
    BabyButtonDescription(
        key="start_tummy",
        translation_key="start_tummy",
        starts="tummy_time",
        offered=lambda baby: not baby.get("tummy_entry_id"),
    ),
    BabyButtonDescription(
        key="end_tummy",
        translation_key="end_tummy",
        ends="tummy_entry_id",
        offered=lambda baby: bool(baby.get("tummy_entry_id")),
    ),
)

_BY_KEY = {description.key: description for description in BUTTONS}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BabyLogBookConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Six per Baby, and six more for a Baby who arrives later."""
    async_add_baby_entities(entry.runtime_data, async_add_entities, BabyButton, tuple(_BY_KEY))


class BabyButton(BabyEntity, ButtonEntity):
    """One press, one revision."""

    entity_description: BabyButtonDescription

    def __init__(self, coordinator: BabyLogBookCoordinator, baby_id: str, key: str) -> None:
        """Take the description that says what this button does."""
        super().__init__(coordinator, baby_id, key)
        self.entity_description = _BY_KEY[key]

    @property
    def available(self) -> bool:
        """Offered only where the app would offer it — convenience, not a gate."""
        return super().available and self.entity_description.offered(self.baby)

    async def async_press(self) -> None:
        """Queue the revision, and try to send it at once."""
        description = self.entity_description
        if description.ends:
            entry_id = self.baby.get(description.ends)
            if not isinstance(entry_id, str) or not entry_id:
                # The read that made this button available said there was one;
                # by the time it was pressed there was not. Nothing to end.
                return
            await self.coordinator.async_write(
                entry_id, {"ended_at": self.coordinator.client.merge_at()}
            )
            return

        assert description.starts is not None
        fields = self.coordinator.creation(self.baby_id, description.starts)
        fields.update(description.extra or {})
        await self.coordinator.async_write(uuid.uuid4().hex, fields)
