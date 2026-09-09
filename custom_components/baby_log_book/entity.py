"""What every entity in this integration has in common.

Two devices' worth: **one per Baby**, named as the Household spelled her, and
**one for the Household**. Names are translated rather than hardcoded, and the
`unique_id` keys are byte-for-byte the payload's field names — so a family's
automations couple to the wire, and renaming one is a wire change.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BabyLogBookCoordinator

MANUFACTURER = "Baby Log Book"

#: What tells a Baby's device from the Household's, since both are ours.
BABY_PREFIX = "baby_"


def baby_device_id(baby_id: str) -> tuple[str, str]:
    """A Baby's device identifier, told apart from a Household's by its prefix."""
    return (DOMAIN, f"{BABY_PREFIX}{baby_id}")


def household_device_id(household_id: str) -> tuple[str, str]:
    """The Household's own device — the one the two diagnostics hang off."""
    return (DOMAIN, f"household_{household_id}")


def baby_of(identifiers: Iterable[tuple[str, str]]) -> str | None:
    """The Baby a device stands for, or nothing if it stands for a Household.

    The inverse of `baby_device_id`, and here beside it on purpose: the prefix
    is a format two callers have to agree on, and one file should own it.
    """
    for domain, identifier in identifiers:
        if domain == DOMAIN and identifier.startswith(BABY_PREFIX):
            return identifier.removeprefix(BABY_PREFIX)
    return None


class BabyLogBookEntity(CoordinatorEntity[BabyLogBookCoordinator]):
    """Shared naming for everything this integration adds."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BabyLogBookCoordinator, key: str) -> None:
        """Take the payload key as the translation key; they are the same word."""
        super().__init__(coordinator)
        self.key = key
        self._attr_translation_key = key


class BabyEntity(BabyLogBookEntity):
    """One data point about one Baby."""

    def __init__(self, coordinator: BabyLogBookCoordinator, baby_id: str, key: str) -> None:
        """Hang the entity off the Baby's device."""
        super().__init__(coordinator, key)
        self.baby_id = baby_id
        self._attr_unique_id = f"{baby_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={baby_device_id(baby_id)},
            name=coordinator.baby_name(baby_id),
            manufacturer=MANUFACTURER,
            model="Baby",
        )

    @property
    def baby(self) -> Mapping[str, Any]:
        """This Baby's slice of the last payload, or nothing if she is gone."""
        data = self.coordinator.data
        if data is None:
            return {}
        return data.babies.get(self.baby_id) or {}

    @property
    def available(self) -> bool:
        """A Baby the payload has stopped carrying has a stale device."""
        return super().available and bool(self.baby)


class HouseholdEntity(BabyLogBookEntity):
    """One fact about the Household, or about this Hub's grip on it."""

    def __init__(self, coordinator: BabyLogBookCoordinator, key: str) -> None:
        """Hang the entity off the Household's device."""
        super().__init__(coordinator, key)
        self._attr_unique_id = f"{coordinator.household_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={household_device_id(coordinator.household_id)},
            name=coordinator.household_name,
            manufacturer=MANUFACTURER,
            model="Household",
            configuration_url=coordinator.origin,
        )


@callback
def async_add_baby_entities(
    coordinator: BabyLogBookCoordinator,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[BabyLogBookCoordinator, str, str], Entity],
    keys: Sequence[str],
    first_use_keys: Sequence[str] = (),
) -> None:
    """Add every Baby's entities now, and any Baby who arrives later.

    Two existence rules live here. A Baby added after setup appears without
    re-adding the integration (`dynamic-devices`). And the appear-on-first-use
    pair is created from what the payload carries and **never removed once
    created**: the rule only adds, because a family's dashboard must not lose
    a card because a quiet week went by.
    """
    known: set[tuple[str, str]] = set()

    @callback
    def _async_add() -> None:
        data = coordinator.data
        if data is None:
            return
        fresh: list[Entity] = []
        for baby_id, baby in data.babies.items():
            wanted: Iterable[str] = (*keys, *(k for k in first_use_keys if k in baby))
            for key in wanted:
                if (baby_id, key) in known:
                    continue
                known.add((baby_id, key))
                fresh.append(factory(coordinator, baby_id, key))
        if fresh:
            async_add_entities(fresh)

    _async_add()
    coordinator.config_entry.async_on_unload(coordinator.async_add_listener(_async_add))
