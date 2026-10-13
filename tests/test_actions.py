"""Six buttons and two services — what a wall offers, and what it writes."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.baby_log_book.const import (
    DOMAIN,
    SERVICE_LOG_BOTTLE_FEED,
    SERVICE_LOG_NAPPY,
)

from .conftest import (
    BABY_ID,
    HOUSEHOLD_ID,
    ORIGIN,
    baby,
    mock_push,
    mock_state,
    setup_entry,
    state_of,
    state_payload,
)

PUSH_URL = f"{ORIGIN}/api/sync/push"


def pushed(mocker: AiohttpClientMocker) -> dict[str, Any]:
    """The one revision the last push carried."""
    body: dict[str, Any] = next(
        call[2] for call in mocker.mock_calls if call[1].path == "/api/sync/push"
    )
    assert len(body["revisions"]) == 1
    revision: dict[str, Any] = body["revisions"][0]
    return revision


def all_pushed(mocker: AiohttpClientMocker) -> list[dict[str, Any]]:
    """Every revision every push carried, in order."""
    return [
        revision
        for call in mocker.mock_calls
        if call[1].path == "/api/sync/push"
        for revision in call[2]["revisions"]
    ]


async def press(hass: HomeAssistant, entity_id: str) -> None:
    """Press one button."""
    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: entity_id}, blocking=True)


def device_of(hass: HomeAssistant, identifier: str) -> str:
    """The Home Assistant device id behind one of our identifiers."""
    device = dr.async_get(hass).async_get_device({(DOMAIN, identifier)})
    assert device is not None
    return device.id


# --- the six buttons ------------------------------------------------------


async def test_sleep_starts_a_sleep(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """An ordinary creation: a Live Session is an Entry with no end."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    aioclient_mock.clear_requests()
    mock_push(aioclient_mock)

    await press(hass, "button.emma_sleep")

    revision = pushed(aioclient_mock)
    assert revision["fields"]["type"] == "sleep"
    assert revision["fields"]["baby_id"] == BABY_ID
    assert revision["fields"]["ended_at"] is None
    assert revision["entity_id"] != BABY_ID


async def test_feed_starts_a_breast_feed_with_the_apps_default_side(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """The phone owns `side`; the wall's Feed button starts with the default."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    aioclient_mock.clear_requests()
    mock_push(aioclient_mock)

    await press(hass, "button.emma_feed")

    fields = pushed(aioclient_mock)["fields"]
    assert fields["type"] == "breast_feed"
    assert fields["side"] == "both"


async def test_the_enders_address_the_entry_the_payload_names(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A Sleep begun on a phone is stopped at the wall by its id."""
    mock_state(
        aioclient_mock,
        state_payload([baby(asleep=True, sleep_entry_id="s-77", asleep_since=1)]),
    )
    assert await setup_entry(hass, entry, aioclient_mock)
    aioclient_mock.clear_requests()
    mock_push(aioclient_mock)

    await press(hass, "button.emma_she_s_awake")

    revision = pushed(aioclient_mock)
    assert revision["entity_id"] == "s-77"
    assert set(revision["fields"]) == {"ended_at"}


@pytest.mark.parametrize(
    ("entity_id", "available_when"),
    [
        ("button.emma_sleep", {"asleep": False}),
        ("button.emma_she_s_awake", {"asleep": True, "sleep_entry_id": "s-1"}),
        ("button.emma_end_feed", {"feeding": True, "feed_entry_id": "f-1"}),
        ("button.emma_tummy_time", {"tummy_entry_id": None}),
        ("button.emma_off_her_tummy", {"tummy_entry_id": "t-1"}),
    ],
)
async def test_availability_mirrors_the_apps_own_reflow(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    entity_id: str,
    available_when: dict[str, Any],
) -> None:
    """Convenience, not enforcement — the server holds the rules regardless."""
    mock_state(aioclient_mock, state_payload([baby(**available_when)]))
    assert await setup_entry(hass, entry, aioclient_mock)
    assert state_of(hass, entity_id).state != STATE_UNAVAILABLE


async def test_no_sleep_button_while_one_runs(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """The nonsense presses are the ones reflow blocks."""
    mock_state(aioclient_mock, state_payload([baby(asleep=True, sleep_entry_id="s-1")]))
    assert await setup_entry(hass, entry, aioclient_mock)

    assert state_of(hass, "button.emma_sleep").state == STATE_UNAVAILABLE
    assert state_of(hass, "button.emma_off_her_tummy").state == STATE_UNAVAILABLE
    # The Feed button is never withheld: a Feed while asleep keeps the Sleep.
    assert state_of(hass, "button.emma_feed").state != STATE_UNAVAILABLE


async def test_a_race_that_loses_its_entry_writes_nothing(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """The read said there was one; by the press there was not."""
    mock_state(aioclient_mock, state_payload([baby(asleep=True, sleep_entry_id="s-1")]))
    assert await setup_entry(hass, entry, aioclient_mock)

    button = hass.data["entity_components"]["button"].get_entity("button.emma_she_s_awake")
    aioclient_mock.clear_requests()
    mock_state(aioclient_mock, state_payload([baby()]), etag='"8-x-0"')
    mock_push(aioclient_mock)
    await entry.runtime_data.async_refresh()

    await button.async_press()
    assert entry.runtime_data.outbox == []


async def test_no_delete_surface(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A mis-press waits for a phone. Deliberately absent, not forgotten."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    assert "delete" not in str(hass.services.async_services_for_domain(DOMAIN))


# --- the two services -----------------------------------------------------


async def test_the_services_register_without_an_entry(hass: HomeAssistant) -> None:
    """So an automation referring to them validates when nothing is loaded."""
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, DOMAIN, {})
    assert hass.services.has_service(DOMAIN, SERVICE_LOG_BOTTLE_FEED)
    assert hass.services.has_service(DOMAIN, SERVICE_LOG_NAPPY)


async def test_a_bottle_feed_targets_the_babys_device(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """There is never a raw baby id in the call schema."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    aioclient_mock.clear_requests()
    mock_push(aioclient_mock)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_LOG_BOTTLE_FEED,
        {
            ATTR_DEVICE_ID: device_of(hass, f"baby_{BABY_ID}"),
            "volume_ml": 120,
            "contents": "formula",
        },
        blocking=True,
    )

    fields = pushed(aioclient_mock)["fields"]
    assert fields["type"] == "bottle_feed"
    assert fields["baby_id"] == BABY_ID
    assert fields["volume_ml"] == 120
    assert fields["contents"] == "formula"
    assert "leftover_ml" not in fields


async def test_the_device_picker_offers_the_babies_and_nothing_else(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A device field, not a `target`, which hassfest refuses with a device filter on it.

    A target would also take entities, areas and labels, none of which the
    handler can resolve to a Baby.
    """
    from homeassistant.helpers.service import async_get_all_descriptions

    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    descriptions = await async_get_all_descriptions(hass)
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)

    for service in (SERVICE_LOG_BOTTLE_FEED, SERVICE_LOG_NAPPY):
        description = descriptions[DOMAIN][service]
        assert "target" not in description
        field = description["fields"][ATTR_DEVICE_ID]
        assert field["required"] is True
        selector = field["selector"]["device"]
        assert selector["multiple"] is True
        (device_filter,) = selector["filter"]
        assert device_filter["integration"] == DOMAIN
        offered = [device.id for device in devices if device.model == device_filter["model"]]
        assert offered == [device_of(hass, f"baby_{BABY_ID}")]


async def test_a_script_that_names_the_baby_as_a_target_still_logs(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """The README once put the device under `target:`, and scripts in the wild still do."""
    from homeassistant.helpers.service import async_call_from_config

    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    aioclient_mock.clear_requests()
    mock_push(aioclient_mock)

    await async_call_from_config(
        hass,
        {
            "action": f"{DOMAIN}.{SERVICE_LOG_BOTTLE_FEED}",
            "target": {ATTR_DEVICE_ID: device_of(hass, f"baby_{BABY_ID}")},
            "data": {"volume_ml": 120},
        },
        blocking=True,
    )

    fields = pushed(aioclient_mock)["fields"]
    assert fields["baby_id"] == BABY_ID
    assert fields["volume_ml"] == 120


async def test_two_babies_get_one_entry_each(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A list of devices logs the same nappy for every Baby named."""
    mock_state(
        aioclient_mock,
        state_payload([baby(), baby(id="b2", name="Mia")]),
    )
    assert await setup_entry(hass, entry, aioclient_mock)
    aioclient_mock.clear_requests()
    mock_push(aioclient_mock)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_LOG_NAPPY,
        {
            ATTR_DEVICE_ID: [device_of(hass, f"baby_{BABY_ID}"), device_of(hass, "baby_b2")],
            "pee": True,
            "poop": False,
        },
        blocking=True,
    )

    revisions = all_pushed(aioclient_mock)
    assert [revision["fields"]["baby_id"] for revision in revisions] == [BABY_ID, "b2"]
    assert all(revision["fields"]["type"] == "nappy" for revision in revisions)


async def test_a_nappy_is_one_entry(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Pee and poop are two facts about one event."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    aioclient_mock.clear_requests()
    mock_push(aioclient_mock)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_LOG_NAPPY,
        {
            ATTR_DEVICE_ID: device_of(hass, f"baby_{BABY_ID}"),
            "pee": True,
            "poop": True,
            "where": "potty",
            "consistency": "soft",
        },
        blocking=True,
    )

    fields = pushed(aioclient_mock)["fields"]
    assert fields["type"] == "nappy"
    assert (fields["pee"], fields["poop"]) == (True, True)
    assert fields["where"] == "potty"
    assert fields["consistency"] == "soft"


async def test_a_leftover_rides_along_when_it_is_given(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """For a bottle logged complete, with what came back in it."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    aioclient_mock.clear_requests()
    mock_push(aioclient_mock)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_LOG_BOTTLE_FEED,
        {
            ATTR_DEVICE_ID: device_of(hass, f"baby_{BABY_ID}"),
            "volume_ml": 180,
            "leftover_ml": 30,
        },
        blocking=True,
    )
    assert pushed(aioclient_mock)["fields"]["leftover_ml"] == 30


async def test_the_household_device_is_not_a_baby(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Targeting it is a mistake the caller is told about."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)

    with pytest.raises(ServiceValidationError) as refused:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_LOG_NAPPY,
            {
                ATTR_DEVICE_ID: device_of(hass, f"household_{HOUSEHOLD_ID}"),
                "pee": True,
                "poop": False,
            },
            blocking=True,
        )
    assert refused.value.translation_key == "not_a_baby"


async def test_an_unknown_device_is_refused(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Nothing is written on a target that means nothing here."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_LOG_NAPPY,
            {ATTR_DEVICE_ID: "nope", "pee": True, "poop": False},
            blocking=True,
        )


async def test_an_unloaded_entry_is_refused(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """An automation may fire while the entry is down; it says so plainly."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    device_id = device_of(hass, f"baby_{BABY_ID}")

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError) as refused:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_LOG_NAPPY,
            {ATTR_DEVICE_ID: device_id, "pee": True, "poop": False},
            blocking=True,
        )
    assert refused.value.translation_key == "entry_not_loaded"
