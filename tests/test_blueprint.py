"""The shipped blueprint, loaded into Home Assistant and driven.

A blueprint is YAML nobody type-checks: the selectors, the `!input` wiring and
the three trigger templates are only ever proved by a real automation built from
it. So that is what this does — the same file HACS hands a family, imported into
the same Home Assistant the rest of the suite runs against.
"""

from __future__ import annotations

import asyncio
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .conftest import baby, mock_state, setup_entry, state_payload

BLUEPRINT = (
    Path(__file__).parents[1] / "blueprints/automation/baby_log_book/announce_what_is_due.yaml"
)
PATH = "baby_log_book/announce_what_is_due.yaml"
AUTOMATION_DOMAIN = "automation"

SPEAKER = "media_player.hall"
TTS = "tts.piper"
#: A speaker's own announcement volume, the way a Sendspin player exposes it.
ANNOUNCE_SETTING = "number.hall_announce_volume"

#: Her three instants, and the Household's four settings, as this blueprint
#: expects to be pointed at them.
WIRING = {
    "feed_due": "sensor.emma_feed_due",
    "wake_window_up": "sensor.emma_wake_window_up",
    "bottle_runs_out": "sensor.emma_bottle_life_runs_out",
    "feeding_flag": "binary_sensor.emma_feeding",
    "asleep_flag": "binary_sensor.emma_asleep",
    "night_start": "sensor.zuhause_night_start",
    "day_start": "sensor.zuhause_day_start",
    "feed_reminder": "sensor.zuhause_feed_reminder",
    "sleep_reminder": "sensor.zuhause_sleep_reminder",
    "speaker": SPEAKER,
    "tts_engine": TTS,
}


def in_minutes(minutes: float) -> int:
    """An instant that many minutes from now, in epoch milliseconds.

    Relative to the wall clock rather than the suite's frozen `NOW_MS`, because
    the trigger templates compare against `now()`.
    """
    return int((dt_util.utcnow().timestamp() + minutes * 60) * 1000)


def her(**overrides: Any) -> dict[str, Any]:
    """Emma, with nothing due for ten hours unless a test says otherwise.

    The suite's own fixture puts her instants around a frozen `NOW_MS` that is
    long past, and every one of those would arrive here as an instant that has
    come due. A test about a feed says so by naming the feed.
    """
    return baby(**{"feed_due": in_minutes(600), "wake_window_up": in_minutes(600), **overrides})


def a_night_around_now() -> dict[str, Any]:
    """A night window that certainly contains this moment, and its overrides."""
    now = dt_util.now()
    return {
        "use_app_night": False,
        "night_start_override": (now - timedelta(hours=1)).strftime("%H:%M:%S"),
        "night_end_override": (now + timedelta(hours=1)).strftime("%H:%M:%S"),
    }


def a_day_around_now() -> dict[str, Any]:
    """A night window that certainly does not contain this moment."""
    now = dt_util.now()
    return {
        "use_app_night": False,
        "night_start_override": (now + timedelta(hours=2)).strftime("%H:%M:%S"),
        "night_end_override": (now + timedelta(hours=3)).strftime("%H:%M:%S"),
    }


async def _settle() -> None:
    """Let every ready callback run, without waiting on one that is parked."""
    for _ in range(6):
        await asyncio.sleep(0)


@pytest.fixture
def spoken(hass: HomeAssistant) -> list[ServiceCall]:
    """Every `tts.speak` the automation makes."""
    calls: list[ServiceCall] = async_mock_service(hass, "tts", "speak")
    return calls


@pytest.fixture
def volumes(hass: HomeAssistant) -> list[ServiceCall]:
    """Every `media_player.volume_set` it makes."""
    calls: list[ServiceCall] = async_mock_service(hass, "media_player", "volume_set")
    return calls


@pytest.fixture
def settings(hass: HomeAssistant) -> list[ServiceCall]:
    """Every `number.set_value` it makes."""
    calls: list[ServiceCall] = async_mock_service(hass, "number", "set_value")
    return calls


async def build(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    mocker: AiohttpClientMocker,
    **inputs: Any,
) -> None:
    """Import the shipped blueprint and stand one automation on it.

    Set up against a Household with nothing due for ten hours, because a
    template trigger fires on the **change** into true and never on the state it
    finds at startup. That is the behaviour a family wants — a restart at 02:00
    must not announce everything that is already overdue — so every test below
    lets the instant arrive afterwards, through `arrives`.
    """
    shutil.copytree(
        BLUEPRINT.parent,
        Path(hass.config.path("blueprints/automation/baby_log_book")),
        dirs_exist_ok=True,
    )
    mock_state(
        mocker,
        state_payload([her()]),
    )
    assert await setup_entry(hass, entry, mocker)

    # A speaker that is on and already turned up, so the restore has something
    # to put back.
    hass.states.async_set(SPEAKER, "idle", {"volume_level": 0.8})
    hass.states.async_set(ANNOUNCE_SETTING, "50", {"min": 0, "max": 100, "step": 1})

    assert await async_setup_component(
        hass,
        AUTOMATION_DOMAIN,
        {
            AUTOMATION_DOMAIN: {
                "use_blueprint": {"path": PATH, "input": {**WIRING, **inputs}},
            }
        },
    )
    await hass.async_block_till_done()


async def arrives(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    mocker: AiohttpClientMocker,
    payload: dict[str, Any],
) -> None:
    """The next read of the Household, and whatever it makes due."""
    mocker.clear_requests()
    mock_state(mocker, payload, etag='"8-2026-08-17-0"')
    await entry.runtime_data.async_refresh()

    # Never block on the run itself: it parks at `wait_for_trigger` for thirty
    # seconds, and `async_block_till_done` would sit out every one of them. Yield
    # to the loop instead and let the speaker finish saying it, which is what
    # releases the wait — several rounds, because the automation is queued and
    # one run per instant that came due goes through here.
    for _ in range(8):
        await _settle()
        hass.states.async_set(SPEAKER, "playing", {"volume_level": 0.8})
        await _settle()
        hass.states.async_set(SPEAKER, "idle", {"volume_level": 0.8})
    await _settle()


async def test_a_feed_is_announced_at_the_lead_the_app_states(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    spoken: list[ServiceCall],
    volumes: list[ServiceCall],
) -> None:
    """Ten minutes' warning, taken from `feed_reminder`, never typed here."""
    await build(hass, entry, aioclient_mock, **a_day_around_now(), feed_lead_min=1)
    # The Household states 600 seconds; this is inside that, and outside the one
    # minute the blueprint would fall back to if it read nothing.
    await arrives(hass, entry, aioclient_mock, state_payload([her(feed_due=in_minutes(8))]))

    assert [call.data["message"] for call in spoken] == ["A feed is due."]
    assert volumes[0].data["volume_level"] == 0.35


async def test_nothing_is_said_while_the_feed_is_still_far_off(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    spoken: list[ServiceCall],
    volumes: list[ServiceCall],
) -> None:
    """The lead is a lead, not a licence to announce the moment HA starts."""
    await build(hass, entry, aioclient_mock, **a_day_around_now())
    await arrives(hass, entry, aioclient_mock, state_payload([her(feed_due=in_minutes(45))]))

    assert spoken == []


async def test_it_announces_quietly_inside_the_night_window(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    spoken: list[ServiceCall],
    volumes: list[ServiceCall],
) -> None:
    """Three in the morning is the whole reason the night window is read."""
    await build(hass, entry, aioclient_mock, **a_night_around_now())
    await arrives(hass, entry, aioclient_mock, state_payload([her(feed_due=in_minutes(8))]))

    assert len(spoken) == 1
    assert volumes[0].data["volume_level"] == 0.15


async def test_it_says_nothing_at_night_when_that_is_what_night_is_for(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    spoken: list[ServiceCall],
    volumes: list[ServiceCall],
) -> None:
    """Silent means silent: not a quiet announcement, and not a volume change."""
    await build(hass, entry, aioclient_mock, **a_night_around_now(), night_mode="silent")
    await arrives(hass, entry, aioclient_mock, state_payload([her(feed_due=in_minutes(8))]))

    assert spoken == []
    assert volumes == []


async def test_it_holds_its_tongue_while_she_is_already_feeding(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    spoken: list[ServiceCall],
    volumes: list[ServiceCall],
) -> None:
    """The app's own rule: no reminder while she is already at it."""
    await build(hass, entry, aioclient_mock, **a_day_around_now())
    await arrives(
        hass, entry, aioclient_mock, state_payload([her(feed_due=in_minutes(8), feeding=True)])
    )

    assert spoken == []


async def test_it_speaks_whether_or_not_caregiving_is_on(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    spoken: list[ServiceCall],
    volumes: list[ServiceCall],
) -> None:
    """Caregiving off means the Parents have her — and the wall is theirs."""
    await build(hass, entry, aioclient_mock, **a_day_around_now())
    await arrives(
        hass, entry, aioclient_mock, state_payload([her(feed_due=in_minutes(8))], caregiving=False)
    )

    assert [call.data["message"] for call in spoken] == ["A feed is due."]


async def test_the_wake_window_and_the_bottle_speak_their_own_words(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    spoken: list[ServiceCall],
    volumes: list[ServiceCall],
) -> None:
    """Three triggers, three messages, one automation."""
    await build(hass, entry, aioclient_mock, **a_day_around_now())
    await arrives(
        hass,
        entry,
        aioclient_mock,
        state_payload(
            [
                her(
                    feed_due=in_minutes(600),
                    # `sleep_reminder` is 300 seconds *after* the window is up.
                    wake_window_up=in_minutes(-10),
                    bottle_runs_out=in_minutes(5),
                    bottle_open=True,
                )
            ]
        ),
    )

    assert sorted(call.data["message"] for call in spoken) == [
        "The open bottle is about to run out.",
        "The wake window is up.",
    ]


async def test_an_automation_from_the_older_blueprint_still_loads(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    spoken: list[ServiceCall],
    volumes: list[ServiceCall],
) -> None:
    """The `caregiving` input is gone; one still naming it is not an error."""
    await build(
        hass,
        entry,
        aioclient_mock,
        **a_day_around_now(),
        caregiving="binary_sensor.zuhause_caregiving",
    )
    await arrives(
        hass, entry, aioclient_mock, state_payload([her(feed_due=in_minutes(8))], caregiving=False)
    )

    assert [call.data["message"] for call in spoken] == ["A feed is due."]


async def test_a_speaker_with_its_own_announcement_volume_gets_the_level_written_there(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    spoken: list[ServiceCall],
    volumes: list[ServiceCall],
    settings: list[ServiceCall],
) -> None:
    """A Sendspin player plays every announcement at its own number, so 0.35 goes there as 35.

    Its media player volume is left alone: set it too and the two restores race,
    and the music afterwards comes out at the announcement's level.
    """
    await build(
        hass, entry, aioclient_mock, **a_day_around_now(), announce_volume_setting=ANNOUNCE_SETTING
    )
    await arrives(hass, entry, aioclient_mock, state_payload([her(feed_due=in_minutes(8))]))

    assert len(spoken) == 1
    assert [(call.data["entity_id"], call.data["value"]) for call in settings] == [
        ([ANNOUNCE_SETTING], 35)
    ]
    assert volumes == []


async def test_the_announcement_volume_setting_is_quieter_at_night_too(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    spoken: list[ServiceCall],
    settings: list[ServiceCall],
) -> None:
    """The night volume is scaled over the number's own range, not assumed 0 to 100."""
    hass.states.async_set(ANNOUNCE_SETTING, "0.5", {"min": 0, "max": 1, "step": 0.05})
    await build(
        hass,
        entry,
        aioclient_mock,
        **a_night_around_now(),
        announce_volume_setting=ANNOUNCE_SETTING,
    )
    hass.states.async_set(ANNOUNCE_SETTING, "0.5", {"min": 0, "max": 1, "step": 0.05})
    await arrives(hass, entry, aioclient_mock, state_payload([her(feed_due=in_minutes(8))]))

    assert len(spoken) == 1
    assert [call.data["value"] for call in settings] == [0.15]
