"""Baby Log Book — a Household's day on a wall panel.

Setup is two halves. `async_setup` registers the two actions, so an automation
referring to them validates **even when no entry is loaded**; `async_setup_entry`
builds the client and the coordinator for one Household and hands them to the
three platforms.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.const import ATTR_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import BabyLogBookClient
from .const import (
    ATTR_CONSISTENCY,
    ATTR_CONTENTS,
    ATTR_LEFTOVER_ML,
    ATTR_PEE,
    ATTR_POOP,
    ATTR_VOLUME_ML,
    ATTR_WHERE,
    BOTTLE_CONTENTS,
    CONF_ORIGIN,
    CONF_SESSION,
    DOMAIN,
    MAX_VOLUME_ML,
    NAPPY_CONSISTENCY,
    NAPPY_WHERE,
    SERVICE_LOG_BOTTLE_FEED,
    SERVICE_LOG_NAPPY,
)
from .coordinator import BabyLogBookConfigEntry, BabyLogBookCoordinator
from .entity import baby_of
from .issues import async_clear_all

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

#: There is deliberately no `baby_id` field in either schema. A call names the
#: Baby's device and the integration resolves it — the id a Hub sends is a
#: client-supplied id, never a capability (ADR-0020).
_TARGET: dict[Any, Any] = {vol.Required(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string])}

BOTTLE_SCHEMA = vol.Schema(
    {
        **_TARGET,
        vol.Required(ATTR_VOLUME_ML): vol.All(vol.Coerce(int), vol.Range(1, MAX_VOLUME_ML)),
        vol.Optional(ATTR_CONTENTS): vol.In(BOTTLE_CONTENTS),
        vol.Optional(ATTR_LEFTOVER_ML): vol.All(vol.Coerce(int), vol.Range(0, MAX_VOLUME_ML)),
    }
)

NAPPY_SCHEMA = vol.Schema(
    {
        **_TARGET,
        vol.Required(ATTR_PEE): cv.boolean,
        vol.Required(ATTR_POOP): cv.boolean,
        vol.Optional(ATTR_WHERE): vol.In(NAPPY_WHERE),
        vol.Optional(ATTR_CONSISTENCY): vol.In(NAPPY_CONSISTENCY),
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the two actions, loaded entry or not."""

    async def _async_log_bottle_feed(call: ServiceCall) -> None:
        for coordinator, baby_id in _targets(hass, call):
            fields: dict[str, Any] = {
                **coordinator.creation(baby_id, "bottle_feed"),
                ATTR_VOLUME_ML: call.data[ATTR_VOLUME_ML],
                ATTR_CONTENTS: call.data.get(ATTR_CONTENTS),
            }
            if (leftover := call.data.get(ATTR_LEFTOVER_ML)) is not None:
                fields[ATTR_LEFTOVER_ML] = leftover
            await coordinator.async_write(uuid.uuid4().hex, fields)

    async def _async_log_nappy(call: ServiceCall) -> None:
        for coordinator, baby_id in _targets(hass, call):
            await coordinator.async_write(
                uuid.uuid4().hex,
                {
                    **coordinator.creation(baby_id, "nappy"),
                    ATTR_PEE: call.data[ATTR_PEE],
                    ATTR_POOP: call.data[ATTR_POOP],
                    ATTR_WHERE: call.data.get(ATTR_WHERE),
                    ATTR_CONSISTENCY: call.data.get(ATTR_CONSISTENCY),
                },
            )

    hass.services.async_register(
        DOMAIN, SERVICE_LOG_BOTTLE_FEED, _async_log_bottle_feed, schema=BOTTLE_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_LOG_NAPPY, _async_log_nappy, schema=NAPPY_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BabyLogBookConfigEntry) -> bool:
    """Bind one Household to this Home Assistant."""
    client = BabyLogBookClient(
        async_get_clientsession(hass),
        entry.data[CONF_ORIGIN],
        entry.data[CONF_SESSION],
    )
    coordinator = BabyLogBookCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_listen()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BabyLogBookConfigEntry) -> bool:
    """Let go of everything; the stream is a background task of the entry's."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: BabyLogBookConfigEntry) -> None:
    """An entry that is gone takes its three repair issues with it.

    `member_removed` is persistent on purpose — nothing about a Removal heals,
    so it has to survive a restart — and the way back from one is to delete this
    entry and add the integration again. Left standing it would be a red card
    about a Household this Home Assistant no longer has, and not a fixable one,
    so nobody could dismiss it either.
    """
    async_clear_all(hass, entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: BabyLogBookConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Whether this device may be deleted by hand.

    A Baby the payload has stopped carrying is deleted in the app, and her
    device is left standing so nobody loses history by surprise — stale, and
    **removable**. A Baby who is still there is not: deleting her device here
    would only make it come back on the next read. The Household's own device is
    never removable while the entry is loaded; it is the entry.
    """
    baby_id = baby_of(device.identifiers)
    if baby_id is None:
        return False
    data = entry.runtime_data.data
    return data is None or baby_id not in data.babies


def _targets(hass: HomeAssistant, call: ServiceCall) -> list[tuple[BabyLogBookCoordinator, str]]:
    """Resolve each targeted device to a Baby and the entry that holds her."""
    registry = dr.async_get(hass)
    resolved: list[tuple[BabyLogBookCoordinator, str]] = []
    for device_id in call.data[ATTR_DEVICE_ID]:
        device = registry.async_get(device_id)
        baby_id = baby_of(device.identifiers) if device else None
        if device is None or baby_id is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="not_a_baby",
                translation_placeholders={"device_id": device_id},
            )
        coordinator = _coordinator_of(hass, device.config_entries)
        if coordinator is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_loaded",
                translation_placeholders={"device_id": device_id},
            )
        resolved.append((coordinator, baby_id))
    return resolved


def _coordinator_of(
    hass: HomeAssistant, entry_ids: Mapping[str, Any] | set[str]
) -> BabyLogBookCoordinator | None:
    """The loaded entry behind a device, if there is one."""
    for entry_id in entry_ids:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is not None and entry.domain == DOMAIN and hasattr(entry, "runtime_data"):
            coordinator = entry.runtime_data
            if isinstance(coordinator, BabyLogBookCoordinator):
                return coordinator
    return None
