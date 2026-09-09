"""Three flags per Baby, and the Household's Caregiving switch.

**No Home Assistant device class fits any of them**, and none is forced: the
translated names carry the meaning. These are the automation *conditions* where
the seven instants are the *triggers*.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import BINARY_KEYS, KEY_CAREGIVING
from .coordinator import BabyLogBookConfigEntry, BabyLogBookCoordinator
from .entity import BabyEntity, HouseholdEntity, async_add_baby_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BabyLogBookConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Asleep, feeding and bottle-open per Baby; Caregiving for the Household."""
    coordinator = entry.runtime_data
    async_add_baby_entities(coordinator, async_add_entities, BabyFlag, BINARY_KEYS)
    async_add_entities([CaregivingFlag(coordinator)])


class BabyFlag(BabyEntity, BinarySensorEntity):
    """One of the three states a Baby is in right now."""

    @property
    def is_on(self) -> bool | None:
        """Unknown rather than off when the payload does not say."""
        value = self.baby.get(self.key)
        return value if isinstance(value, bool) else None


class CaregivingFlag(HouseholdEntity, BinarySensorEntity):
    """Whether anybody is looking after her.

    A read, never a capability: nothing about it gates a write, and no total is
    suppressed while it is off. It exists so a family's announce automation can
    hold its tongue — which is how the switch in the app reaches a wall.
    """

    def __init__(self, coordinator: BabyLogBookCoordinator) -> None:
        """One per Household."""
        super().__init__(coordinator, KEY_CAREGIVING)

    @property
    def is_on(self) -> bool | None:
        """The Household's own switch, passed straight through."""
        data = self.coordinator.data
        if data is None:
            return None
        value = data.household.get(KEY_CAREGIVING)
        return value if isinstance(value, bool) else None
