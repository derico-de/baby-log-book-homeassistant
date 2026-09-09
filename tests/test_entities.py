"""Sixteen entities stand for a Baby, and two for the Household."""

from __future__ import annotations

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.baby_log_book import async_remove_config_entry_device
from custom_components.baby_log_book.const import DOMAIN

from .conftest import (
    BABY_ID,
    HOUSEHOLD_ID,
    baby,
    mock_state,
    setup_entry,
    state_of,
    state_payload,
)


async def test_a_baby_has_sixteen_entities(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Seven instants, three flags, four totals and six buttons."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)

    registry = er.async_get(hass)
    mine = [
        item
        for item in registry.entities.values()
        if item.config_entry_id == entry.entry_id and item.unique_id.startswith(BABY_ID)
    ]
    # Four of the six totals; the other two appear on first use.
    assert len(mine) == 7 + 3 + 4 + 6


async def test_the_household_carries_its_two(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A diagnostic staleness tell, and the Caregiving flag."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)

    assert hass.states.get("sensor.zuhause_last_update") is not None
    assert state_of(hass, "sensor.zuhause_pending_writes").state == "0"
    assert state_of(hass, "binary_sensor.zuhause_caregiving").state == "on"


async def test_the_instants_are_instants(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A timestamp device class, so the frontend renders it relative for free."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)

    last_feed = state_of(hass, "sensor.emma_last_feed")
    assert last_feed.attributes["device_class"] == "timestamp"
    assert last_feed.state == "2024-08-27T22:06:40+00:00"


async def test_an_inapplicable_instant_exists_as_unknown(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A cleared Target must never break a family's dashboard."""
    mock_state(aioclient_mock, state_payload([baby(feed_due=None)]))
    assert await setup_entry(hass, entry, aioclient_mock)

    assert state_of(hass, "sensor.emma_feed_due").state == STATE_UNKNOWN


async def test_a_total_declares_its_reset(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """The Household's Day Start instant, never Home Assistant's midnight."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)

    sleep_today = state_of(hass, "sensor.emma_sleep_today")
    assert sleep_today.state == "154"
    assert sleep_today.attributes["state_class"] == "total"
    assert sleep_today.attributes["last_reset"] == "2024-08-28T05:00:00+00:00"
    assert sleep_today.attributes["unit_of_measurement"] == "min"
    assert sleep_today.attributes["device_class"] == "duration"


async def test_the_three_flags_take_no_device_class(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """None fits, and the translated names carry the meaning."""
    mock_state(aioclient_mock, state_payload([baby(asleep=True, feeding=True)]))
    assert await setup_entry(hass, entry, aioclient_mock)

    asleep = state_of(hass, "binary_sensor.emma_asleep")
    assert asleep.state == "on"
    assert "device_class" not in asleep.attributes
    assert state_of(hass, "binary_sensor.emma_feeding").state == "on"
    assert state_of(hass, "binary_sensor.emma_bottle_open").state == "off"


async def test_appear_on_first_use(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Absent until ever logged, created on the first, never removed after."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    assert hass.states.get("sensor.emma_milk_today") is None
    assert hass.states.get("sensor.emma_tummy_time_today") is None

    aioclient_mock.clear_requests()
    mock_state(
        aioclient_mock, state_payload([baby(milk_today=240, tummy_today=12)]), etag='"8-x-0"'
    )
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert state_of(hass, "sensor.emma_milk_today").state == "240"
    assert state_of(hass, "sensor.emma_tummy_time_today").state == "12"

    # A quiet week goes by and the server keeps carrying the field; even if it
    # did not, the entity is never taken away again.
    aioclient_mock.clear_requests()
    mock_state(aioclient_mock, state_payload([baby()]), etag='"9-x-0"')
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert state_of(hass, "sensor.emma_tummy_time_today").state == STATE_UNKNOWN


async def test_a_baby_added_later_appears(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """No re-adding the integration for a second Baby."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    assert hass.states.get("sensor.anton_last_feed") is None

    aioclient_mock.clear_requests()
    mock_state(
        aioclient_mock,
        state_payload([baby(), baby(id="b2", name="Anton")]),
        etag='"8-x-0"',
    )
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("sensor.anton_last_feed") is not None
    devices = dr.async_get(hass).devices
    names = {
        device.name for device in devices.values() if device.config_entries == {entry.entry_id}
    }
    assert names == {"Emma", "Anton", "Zuhause"}


async def test_a_baby_who_goes_away_leaves_a_stale_device(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Her entities go unavailable; the device stays, and is removable."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)

    aioclient_mock.clear_requests()
    mock_state(aioclient_mock, state_payload([]), etag='"8-x-0"')
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert state_of(hass, "sensor.emma_last_feed").state == STATE_UNAVAILABLE
    assert dr.async_get(hass).async_get_device({(DOMAIN, f"baby_{BABY_ID}")}) is not None


async def test_the_two_diagnostics_stay_available_when_nothing_else_is(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A staleness tell that goes unavailable tells nothing."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)

    aioclient_mock.clear_requests()
    aioclient_mock.get("https://babylog.example/api/hub/state", status=500)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert state_of(hass, "sensor.emma_last_feed").state == STATE_UNAVAILABLE
    assert state_of(hass, "sensor.zuhause_last_update").state != STATE_UNAVAILABLE
    assert state_of(hass, "sensor.zuhause_pending_writes").state == "0"


async def test_unique_ids_are_the_payload_keys(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A family's automations couple to the wire, so this may not drift."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)

    registry = er.async_get(hass)
    ids = {item.unique_id for item in registry.entities.values()}
    assert f"{BABY_ID}_last_feed" in ids
    assert f"{BABY_ID}_bottle_open" in ids
    assert f"{HOUSEHOLD_ID}_last_update" in ids


async def test_a_stale_baby_s_device_can_be_removed_by_hand(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Stale *and* removable — the device is left standing, not stranded."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)

    aioclient_mock.clear_requests()
    mock_state(aioclient_mock, state_payload([]), etag='"8-x-0"')
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    registry = dr.async_get(hass)
    stale = registry.async_get_device({(DOMAIN, f"baby_{BABY_ID}")})
    assert stale is not None
    assert await async_remove_config_entry_device(hass, entry, stale)


async def test_a_baby_who_is_still_there_is_not_removable(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Deleting her here would only bring the device back on the next read."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)

    registry = dr.async_get(hass)
    hers = registry.async_get_device({(DOMAIN, f"baby_{BABY_ID}")})
    household = registry.async_get_device({(DOMAIN, f"household_{HOUSEHOLD_ID}")})
    assert hers is not None
    assert household is not None

    assert not await async_remove_config_entry_device(hass, entry, hers)
    # And the Household's device is never removable while the entry is loaded.
    assert not await async_remove_config_entry_device(hass, entry, household)
