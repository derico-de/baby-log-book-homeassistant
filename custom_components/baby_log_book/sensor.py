"""The read surface: seven instants and six totals per Baby, six on the Household.

The seven instants carry the timestamp device class, which is the whole trick:
the frontend renders them relative, live and localized for free — *vor 12
Minuten*, *in 3 Stunden* — so nothing here computes "8 minutes ago" by hand,
and nothing ticks.

The six totals **declare** their reset at the Household's Day Start instant from
the payload. A sensor must never re-derive "today" from Home Assistant's local
midnight: Day Start is a Household setting in the Household Zone, computed
server-side, and it is the only answer.
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    FIRST_USE_TOTAL_KEYS,
    HOUSEHOLD_HOUR_KEYS,
    HOUSEHOLD_NOTICE_KEYS,
    KEY_LAST_UPDATE,
    KEY_PENDING_WRITES,
    TIMESTAMP_KEYS,
    TOTAL_KEYS,
)
from .coordinator import BabyLogBookConfigEntry, BabyLogBookCoordinator
from .entity import BabyEntity, HouseholdEntity, async_add_baby_entities

PARALLEL_UPDATES = 0

#: What a total is measured in, where it is measured in anything. Counts have
#: no unit: *four pees* is not four of a unit anybody names.
_TOTAL_UNITS = {
    "sleep_today": UnitOfTime.MINUTES,
    "tummy_today": UnitOfTime.MINUTES,
    "milk_today": UnitOfVolume.MILLILITERS,
}
_TOTAL_DEVICE_CLASSES = {
    "sleep_today": SensorDeviceClass.DURATION,
    "tummy_today": SensorDeviceClass.DURATION,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BabyLogBookConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Seven instants and six totals per Baby, plus the Household's six."""
    coordinator = entry.runtime_data
    async_add_baby_entities(coordinator, async_add_entities, BabyInstantSensor, TIMESTAMP_KEYS)
    async_add_baby_entities(
        coordinator, async_add_entities, BabyTotalSensor, TOTAL_KEYS, FIRST_USE_TOTAL_KEYS
    )
    async_add_entities(
        [
            LastUpdateSensor(coordinator),
            PendingWritesSensor(coordinator),
            *(HouseholdHourSensor(coordinator, key) for key in HOUSEHOLD_HOUR_KEYS),
            *(HouseholdNoticeSensor(coordinator, key) for key in HOUSEHOLD_NOTICE_KEYS),
        ]
    )


def _number(value: object) -> int | None:
    """A whole number, or nothing. `True` is not a number, whatever Python says."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _instant(value: object) -> datetime | None:
    """Epoch milliseconds as an aware datetime, or nothing at all."""
    milliseconds = _number(value)
    return None if milliseconds is None else dt_util.utc_from_timestamp(milliseconds / 1000)


class BabyInstantSensor(BabyEntity, SensorEntity):
    """One instant, rendered relative by the frontend."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        """`None` — shown as unknown — whenever the instant does not apply.

        A cleared Target must never break a family's dashboard, so the entity
        exists either way.
        """
        return _instant(self.baby.get(self.key))


class BabyTotalSensor(BabyEntity, SensorEntity):
    """One of today's totals, resetting at the Household's Day Start."""

    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator: BabyLogBookCoordinator, baby_id: str, key: str) -> None:
        """Take the unit and device class from the key."""
        super().__init__(coordinator, baby_id, key)
        self._attr_native_unit_of_measurement = _TOTAL_UNITS.get(key)
        self._attr_device_class = _TOTAL_DEVICE_CLASSES.get(key)

    @property
    def native_value(self) -> int | None:
        """The figure the Household's own stats card shows."""
        return _number(self.baby.get(self.key))

    @property
    def last_reset(self) -> datetime | None:
        """Declared, never inferred — the Day Start instant from the payload."""
        data = self.coordinator.data
        if data is None:
            return None
        return _instant(data.household.get("day_reset_at"))


class HouseholdSetting(HouseholdEntity, SensorEntity):
    """One of the four hours and offsets the app states for this Household.

    Diagnostic, because none of it is a reading about her: it is what a family
    typed in Settings, mirrored so their automation can default to it. The point
    is that an hour is stated **once** — a night window written again in Home
    Assistant is a second place to keep it in step, and the two drift.

    Unlike the two tells below, these go unavailable with the coordinator. A
    stale Day Start is worse than no Day Start: an automation reading one would
    be quiet at the wrong hour and never say why.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def _stated(self) -> object:
        """This key's value in the last payload, whatever type it came as."""
        data = self.coordinator.data
        if data is None:
            return None
        return data.household.get(self.key)


class HouseholdHourSensor(HouseholdSetting):
    """An hour as `HH:MM`, or unknown where the Household keeps none.

    `night_start` is the Night **in force** rather than the stored column, so a
    Household whose Night Start equals its Day Start reads unknown here — which
    is what it means: no night.
    """

    @property
    def native_value(self) -> str | None:
        """Nothing at all rather than an empty string when it does not apply."""
        stated = self._stated
        return stated if isinstance(stated, str) and stated else None


class HouseholdNoticeSensor(HouseholdSetting):
    """How much warning the app's own reminder gives, in seconds.

    Deliberately no state class: a setting is not a measurement, and a family's
    recorder should not grow long-term statistics for a number typed once.
    """

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS

    @property
    def native_value(self) -> int | None:
        """Seconds before a Feed is due, or after a Wake Window is up."""
        return _number(self._stated)


class HubDiagnostic(HouseholdEntity, SensorEntity):
    """A fact about this Hub's grip on the Household, rather than about her.

    The two of these are the tells entity availability cannot express — *stale
    since 14:02*, *nine presses still waiting* — and they are most worth reading
    precisely when the server is out. So they never go unavailable: a staleness
    tell that goes unavailable tells nothing.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        """Always."""
        return True


class LastUpdateSensor(HubDiagnostic):
    """When this Hub last heard the server.

    It needs no payload field: it is the coordinator's own clock, and a
    not-modified counts as having heard.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: BabyLogBookCoordinator) -> None:
        """One per Household."""
        super().__init__(coordinator, KEY_LAST_UPDATE)

    @property
    def native_value(self) -> datetime | None:
        """The last answer of any kind, `304`s included."""
        return self.coordinator.last_heard


class PendingWritesSensor(HubDiagnostic):
    """How many presses are still waiting to land.

    Visible state, not a condition needing repair — which is why there is no
    repair issue for a backlog.
    """

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: BabyLogBookCoordinator) -> None:
        """One per Household."""
        super().__init__(coordinator, KEY_PENDING_WRITES)

    @property
    def native_value(self) -> int:
        """The outbox depth, bounded at fifty by the coordinator."""
        return len(self.coordinator.outbox)
