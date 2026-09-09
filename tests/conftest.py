"""Fixtures shared by the whole suite.

No live Home Assistant instance is ever started and no live server is ever
called: the `aiohttp` calls are mocked and the Home Assistant side is real.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant, State
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.baby_log_book.const import (
    CONF_DEVICE_ID,
    CONF_HOUSEHOLD_ID,
    CONF_HOUSEHOLD_NAME,
    CONF_MEMBER_ID,
    CONF_ORIGIN,
    CONF_SESSION,
    DOMAIN,
)

ORIGIN = "https://babylog.example"
HOUSEHOLD_ID = "h1"
BABY_ID = "b1"
SERVER_VERSION = "1.25.0"
ETAG = '"7-2026-08-17-0"'

NOW_MS = 1_724_800_000_000
DAY_RESET_MS = 1_724_821_200_000


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load `custom_components/baby_log_book` in every test."""


@pytest.fixture(autouse=True)
def no_stream(request: pytest.FixtureRequest) -> Generator[None]:
    """Hold the live stream still unless a test asks for it.

    The stream is a background task that reconnects for ever; tests that are
    not about it should not be racing it. A test marked `stream` gets the real
    thing.
    """
    if request.node.get_closest_marker("stream"):
        yield
        return
    with patch("custom_components.baby_log_book.coordinator.BabyLogBookCoordinator.async_listen"):
        yield


def baby(**overrides: Any) -> dict[str, Any]:
    """One Baby as `GET /api/hub/state` ships her."""
    payload: dict[str, Any] = {
        "id": BABY_ID,
        "name": "Emma",
        "last_feed": NOW_MS - 3_600_000,
        "feed_due": NOW_MS + 1_800_000,
        "asleep_since": None,
        "awake_since": NOW_MS - 5_400_000,
        "wake_window_up": NOW_MS + 900_000,
        "bottle_runs_out": None,
        "last_poop": NOW_MS - 10_000_000,
        "asleep": False,
        "feeding": False,
        "bottle_open": False,
        "feed_entry_id": None,
        "sleep_entry_id": None,
        "tummy_entry_id": None,
        "feeds_today": 5,
        "sleep_today": 154,
        "pees_today": 4,
        "poops_today": 2,
    }
    payload.update(overrides)
    return payload


def state_payload(babies: list[dict[str, Any]] | None = None, **household: Any) -> dict[str, Any]:
    """A whole answer, version block and all."""
    return {
        "protocol_version": 2,
        "app_version": SERVER_VERSION,
        "git_sha": "abc1234",
        "source": "test",
        "server_time": NOW_MS,
        "cursor": 7,
        "household": {
            "id": HOUSEHOLD_ID,
            "name": "Zuhause",
            "day_reset_at": DAY_RESET_MS,
            "caregiving": True,
            **household,
        },
        "babies": [baby()] if babies is None else babies,
    }


def entry_data() -> dict[str, str]:
    """What a claimed entry holds."""
    return {
        CONF_ORIGIN: ORIGIN,
        CONF_SESSION: "session-token",
        CONF_MEMBER_ID: "m-hub",
        CONF_HOUSEHOLD_ID: HOUSEHOLD_ID,
        CONF_HOUSEHOLD_NAME: "Zuhause",
        CONF_DEVICE_ID: "dev-hub",
    }


@pytest.fixture
def entry() -> MockConfigEntry:
    """A config entry already bound to a Household."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Zuhause",
        unique_id=HOUSEHOLD_ID,
        data=entry_data(),
    )


def mock_state(
    mocker: AiohttpClientMocker,
    payload: dict[str, Any] | None = None,
    *,
    status: int = 200,
    etag: str = ETAG,
) -> None:
    """Register one answer for the derived read."""
    mocker.get(
        f"{ORIGIN}/api/hub/state",
        status=status,
        json=payload if payload is not None else state_payload(),
        headers={"etag": etag},
    )


def mock_push(mocker: AiohttpClientMocker) -> None:
    """A push that takes everything, and says so by name.

    The answer echoes the ids it was sent, because that is what the outbox
    reads: it lets go of exactly what came back settled.
    """

    async def _accept(method: str, url: object, data: dict[str, Any]) -> AiohttpClientMockResponse:
        return AiohttpClientMockResponse(
            method,
            URL(f"{ORIGIN}/api/sync/push"),
            json={
                "cursor": 8,
                "accepted": [revision["id"] for revision in data["revisions"]],
                "rejected": [],
                "server_time": NOW_MS,
            },
        )

    mocker.post(f"{ORIGIN}/api/sync/push", side_effect=_accept)


def mock_stream_endpoint(mocker: AiohttpClientMocker, body: str = "") -> None:
    """Register the live stream, so a background task has something to open."""
    mocker.get(f"{ORIGIN}/api/sync/live", text=body)


async def setup_entry(
    hass: HomeAssistant, entry: MockConfigEntry, mocker: AiohttpClientMocker
) -> bool:
    """Add the entry and let it set up against whatever is registered."""
    entry.add_to_hass(hass)
    mock_stream_endpoint(mocker)
    result = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return result


def state_of(hass: HomeAssistant, entity_id: str) -> State:
    """The state of an entity that must exist, typed as though it does."""
    found = hass.states.get(entity_id)
    assert found is not None, f"{entity_id} is not there"
    return found
