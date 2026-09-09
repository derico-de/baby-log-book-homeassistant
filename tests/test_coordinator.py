"""The coordinator keeps a live picture, and the cadence numbers are contract."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.baby_log_book.api import (
    BabyLogBookClient,
    CannotConnect,
    Lapsed,
    Removed,
)
from custom_components.baby_log_book.const import (
    BACKOFF_BASE_S,
    BACKOFF_CAP_S,
    DOMAIN,
    ISSUE_HOSTING_PAUSED,
    ISSUE_INTEGRATION_OUTDATED,
    ISSUE_MEMBER_REMOVED,
    OUTBOX_LIMIT,
    POLL_LAPSED,
    POLL_STREAM_DOWN,
    POLL_STREAM_HEALTHY,
)
from custom_components.baby_log_book.coordinator import _backoff
from custom_components.baby_log_book.issues import issue_id

from .conftest import (
    NOW_MS,
    ORIGIN,
    mock_push,
    mock_state,
    mock_stream_endpoint,
    setup_entry,
    state_of,
    state_payload,
)

STATE_URL = f"{ORIGIN}/api/hub/state"


def issue_present(hass: HomeAssistant, kind: str, entry: MockConfigEntry) -> Any:
    """The one copy of a repair issue this entry would have raised."""
    return ir.async_get(hass).async_get_issue(DOMAIN, issue_id(kind, entry.entry_id))


# --- the conditional read -------------------------------------------------


async def test_the_etag_is_echoed_verbatim_and_never_parsed(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """The format is the server's freedom, so nothing here reads it."""
    mock_state(aioclient_mock, etag='"anything at all"')
    assert await setup_entry(hass, entry, aioclient_mock)

    aioclient_mock.clear_requests()
    mock_state(aioclient_mock, status=304, etag='"anything at all"')
    mock_stream_endpoint(aioclient_mock)
    await entry.runtime_data.async_refresh()

    sent = [call[3] for call in aioclient_mock.mock_calls if call[1].path == "/api/hub/state"]
    assert sent[0]["if-none-match"] == '"anything at all"'


async def test_not_modified_keeps_the_previous_data(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """And counts as a successful update, so nothing goes unavailable."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    before = entry.runtime_data.data

    aioclient_mock.clear_requests()
    mock_state(aioclient_mock, status=304)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert entry.runtime_data.data is before
    assert entry.runtime_data.last_update_success
    assert state_of(hass, "sensor.emma_last_feed").state != "unavailable"


async def test_a_not_modified_still_counts_as_hearing_the_server(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """It is an answer, and staleness is what the diagnostic is about."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    first = entry.runtime_data.last_heard

    aioclient_mock.clear_requests()
    mock_state(aioclient_mock, status=304)
    await entry.runtime_data.async_refresh()
    assert entry.runtime_data.last_heard >= first


async def test_the_clock_offset_comes_off_every_non_304(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A Hub that was cut off writes the same slightly-late revision a phone would."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)

    client = entry.runtime_data.client
    assert client.offset_ms != 0
    assert abs(client.merge_at() - NOW_MS) < 5_000


# --- the failure taxonomy, at runtime -------------------------------------


async def test_a_stale_session_opens_reauth(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Which asks for a Rescue Link, in the same words as the lost phone."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)

    aioclient_mock.clear_requests()
    aioclient_mock.get(STATE_URL, status=401, json={"code": "unauthenticated"})
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert [flow["context"]["source"] for flow in hass.config_entries.flow.async_progress()] == [
        SOURCE_REAUTH
    ]


async def test_removed_never_opens_reauth(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A re-auth would ask for a Rescue Link that cannot exist."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)

    aioclient_mock.clear_requests()
    aioclient_mock.get(STATE_URL, status=403, json={"code": "removed"})
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.config_entries.flow.async_progress() == []
    issue = issue_present(hass, ISSUE_MEMBER_REMOVED, entry)
    assert issue.severity is ir.IssueSeverity.ERROR
    assert issue.is_fixable is False
    # A full stop: no polling, and the entities say so.
    assert entry.runtime_data.update_interval is None
    assert state_of(hass, "sensor.emma_last_feed").state == "unavailable"


async def test_hosting_paused_polls_gently_and_recovers_quietly(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A billing state, not a defect — and nothing changes while it lasts."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)

    aioclient_mock.clear_requests()
    aioclient_mock.get(STATE_URL, status=402, json={"code": "lapsed"})
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    issue = issue_present(hass, ISSUE_HOSTING_PAUSED, entry)
    assert issue.severity is ir.IssueSeverity.WARNING
    assert entry.runtime_data.update_interval == POLL_LAPSED
    assert state_of(hass, "sensor.emma_last_feed").state == "unavailable"

    aioclient_mock.clear_requests()
    mock_state(aioclient_mock, etag='"8-x-0"')
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert issue_present(hass, ISSUE_HOSTING_PAUSED, entry) is None
    assert entry.runtime_data.update_interval == POLL_STREAM_DOWN
    assert state_of(hass, "sensor.emma_last_feed").state != "unavailable"


async def test_an_answer_this_release_cannot_read(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """The third repair issue: update the integration."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        STATE_URL, json={"app_version": "9.0.0", "babies": []}, headers={"etag": '"x"'}
    )
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert issue_present(hass, ISSUE_INTEGRATION_OUTDATED, entry) is not None
    assert not entry.runtime_data.last_update_success


async def test_a_runtime_outage_keeps_the_cadence(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Entities go unavailable; nothing else changes."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)

    aioclient_mock.clear_requests()
    aioclient_mock.get(STATE_URL, exc=TimeoutError())
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert not entry.runtime_data.last_update_success
    assert entry.runtime_data.update_interval == POLL_STREAM_DOWN
    assert hass.config_entries.flow.async_progress() == []


# --- the failure taxonomy, at setup ---------------------------------------


async def test_a_network_failure_at_setup_is_the_frameworks_retry(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Never a hand-written setup retry loop."""
    aioclient_mock.get(STATE_URL, exc=TimeoutError())
    assert not await setup_entry(hass, entry, aioclient_mock)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_removed_at_setup_is_permanent(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """No retry: there is nothing to come back to."""
    aioclient_mock.get(STATE_URL, status=403, json={"code": "removed"})
    assert not await setup_entry(hass, entry, aioclient_mock)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert issue_present(hass, ISSUE_MEMBER_REMOVED, entry) is not None


async def test_lapsed_at_setup_keeps_the_entry(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Retry after reactivation is a reload."""
    aioclient_mock.get(STATE_URL, status=402, json={"code": "lapsed"})
    assert not await setup_entry(hass, entry, aioclient_mock)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert issue_present(hass, ISSUE_HOSTING_PAUSED, entry) is not None


async def test_a_server_too_old_blocks_every_setup(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """The second half of ADR-0039's dual gate."""
    mock_state(aioclient_mock, state_payload() | {"app_version": "1.24.0"})
    assert not await setup_entry(hass, entry, aioclient_mock)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert "1.25.0" in str(entry.reason)


async def test_no_per_response_version_check_at_runtime(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A rollback mid-flight is an operator act; it surfaces at the next reload."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)

    aioclient_mock.clear_requests()
    mock_state(aioclient_mock, state_payload() | {"app_version": "1.0.0"}, etag='"8-x-0"')
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert entry.runtime_data.last_update_success


# --- the wake signal ------------------------------------------------------


def test_the_backoff_is_exponential_capped_and_jittered() -> None:
    """Base five seconds, cap five minutes, and never a fixed delay."""
    assert all(0 <= _backoff(0) <= BACKOFF_BASE_S for _ in range(20))
    assert all(0 <= _backoff(3) <= BACKOFF_BASE_S * 8 for _ in range(20))
    assert all(0 <= _backoff(40) <= BACKOFF_CAP_S for _ in range(20))
    assert len({_backoff(6) for _ in range(20)}) > 1


async def test_the_stream_flips_the_poll_and_wakes_the_read(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Hello relaxes the poll to its safety net; a wake asks for a read."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    coordinator = entry.runtime_data

    async def _events(_self: object) -> AsyncIterator[str]:
        yield "hello"
        yield "wake"
        coordinator._stopped = True  # one clean pass, then the loop lets go

    refreshes: list[None] = []

    async def _refresh() -> None:
        refreshes.append(None)

    with (
        patch.object(BabyLogBookClient, "async_events", _events),
        patch.object(coordinator, "async_request_refresh", _refresh),
    ):
        await coordinator._async_stream()

    assert refreshes == [None]
    assert coordinator.update_interval == POLL_STREAM_HEALTHY


async def test_a_dropped_stream_polls_at_the_outage_cadence(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Five stale minutes on a wall during an outage would be noticed."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    coordinator = entry.runtime_data
    coordinator.update_interval = POLL_STREAM_HEALTHY

    async def _events(_self: object) -> AsyncIterator[str]:
        raise CannotConnect("gone")
        yield  # pragma: no cover - unreachable, and that is the point

    async def _sleep(_delay: float) -> None:
        """Stand in for the backoff, and end the loop after one pass."""
        coordinator._stopped = True

    with (
        patch.object(BabyLogBookClient, "async_events", _events),
        patch("custom_components.baby_log_book.coordinator.asyncio.sleep", _sleep),
    ):
        await coordinator._async_stream()

    assert coordinator.update_interval == POLL_STREAM_DOWN


@pytest.mark.stream
async def test_the_stream_starts_with_the_entry(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """And is a background task of the entry's, so unloading cancels it."""
    mock_state(aioclient_mock)
    entry.add_to_hass(hass)
    mock_stream_endpoint(aioclient_mock, "event: hello\ndata: 1\n\n")

    with patch(
        "custom_components.baby_log_book.coordinator.BabyLogBookCoordinator._async_stream"
    ) as stream:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert stream.called


# --- the outbox -----------------------------------------------------------


async def test_a_press_goes_down_the_one_write_path(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A plain revision with a client-minted id, and no protocol version."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    aioclient_mock.clear_requests()
    mock_push(aioclient_mock)

    await entry.runtime_data.async_write("e1", {"ended_at": NOW_MS})

    body = aioclient_mock.mock_calls[0][2]
    assert "protocol_version" not in body
    assert body["device_id"] == "dev-hub"
    revision = body["revisions"][0]
    assert revision["kind"] == "entry"
    assert revision["entity_id"] == "e1"
    assert revision["author_id"] == "m-hub"
    assert revision["fields"] == {"ended_at": NOW_MS}
    assert entry.runtime_data.outbox == []


async def test_a_write_that_did_not_land_stays_queued(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Push is insert-only, so retrying after a lost response is a no-op."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{ORIGIN}/api/sync/push", exc=TimeoutError())

    await entry.runtime_data.async_write("e1", {"ended_at": NOW_MS})
    assert len(entry.runtime_data.outbox) == 1
    assert state_of(hass, "sensor.zuhause_pending_writes").state == "1"

    aioclient_mock.clear_requests()
    mock_state(aioclient_mock, etag='"8-x-0"')
    mock_push(aioclient_mock)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert entry.runtime_data.outbox == []
    assert state_of(hass, "sensor.zuhause_pending_writes").state == "0"


async def test_a_write_the_server_refuses_is_let_go(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Retrying for ever would block everything queued behind it."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    aioclient_mock.clear_requests()

    async def _refuse_whatever_arrives(
        method: str, url: object, data: dict[str, Any]
    ) -> AiohttpClientMockResponse:
        rejected = [{"id": r["id"], "reason": "nope"} for r in data["revisions"]]
        return AiohttpClientMockResponse(
            method, URL(f"{ORIGIN}/api/sync/push"), json={"cursor": 7, "rejected": rejected}
        )

    aioclient_mock.post(f"{ORIGIN}/api/sync/push", side_effect=_refuse_whatever_arrives)

    await entry.runtime_data.async_write("e1", {"ended_at": NOW_MS})
    assert entry.runtime_data.outbox == []


async def test_only_what_the_server_settled_leaves_the_outbox(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A press the answer did not account for is still waiting, not lost."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    coordinator = entry.runtime_data
    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{ORIGIN}/api/sync/push", exc=TimeoutError())

    await coordinator.async_write("e1", {"ended_at": NOW_MS})
    await coordinator.async_write("e2", {"ended_at": NOW_MS})
    first, second = (revision["id"] for revision in coordinator.outbox)

    aioclient_mock.clear_requests()
    aioclient_mock.post(
        f"{ORIGIN}/api/sync/push",
        json={"cursor": 8, "accepted": [first], "rejected": []},
    )
    await coordinator._async_flush()

    assert [revision["id"] for revision in coordinator.outbox] == [second]


async def test_a_batch_the_server_would_not_read_at_all(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A malformed batch is not a thing a later attempt fixes either."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{ORIGIN}/api/sync/push", status=400, json={"code": "malformed"})

    await entry.runtime_data.async_write("e1", {"ended_at": NOW_MS})
    assert entry.runtime_data.outbox == []


async def test_the_outbox_bound_raises_rather_than_queuing_silently(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A hub is not a phone: silently queuing feeds for six hours is worse."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{ORIGIN}/api/sync/push", exc=TimeoutError())

    for index in range(OUTBOX_LIMIT):
        await entry.runtime_data.async_write(f"e{index}", {"ended_at": NOW_MS})
    assert len(entry.runtime_data.outbox) == OUTBOX_LIMIT
    assert state_of(hass, "sensor.zuhause_pending_writes").state == str(OUTBOX_LIMIT)

    with pytest.raises(HomeAssistantError) as refused:
        await entry.runtime_data.async_write("one-too-many", {"ended_at": NOW_MS})
    assert refused.value.translation_key == "outbox_full"
    assert len(entry.runtime_data.outbox) == OUTBOX_LIMIT


async def test_a_backlog_raises_no_repair_issue(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A non-empty outbox is visible state, not a condition needing repair."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{ORIGIN}/api/sync/push", exc=TimeoutError())

    await entry.runtime_data.async_write("e1", {"ended_at": NOW_MS})
    assert list(ir.async_get(hass).issues) == []


async def test_the_two_terminal_states_are_raised_once(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A poll every five minutes must not re-raise the same issue for ever."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    coordinator = entry.runtime_data

    coordinator._async_enter_lapsed()
    coordinator._async_enter_lapsed()
    assert issue_present(hass, ISSUE_HOSTING_PAUSED, entry) is not None
    assert coordinator.update_interval == POLL_LAPSED

    coordinator._async_stop_for_removal()
    coordinator._async_stop_for_removal()
    assert coordinator.update_interval is None
    # And a stopped coordinator does not quietly start polling again.
    coordinator._async_stream_down()
    assert coordinator.update_interval is None


async def test_the_stream_stops_itself_on_the_two_terminal_states(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """The stream 402s and 403s too, so it does not hammer either."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    coordinator = entry.runtime_data

    async def _removed(_self: object) -> AsyncIterator[str]:
        raise Removed("gone")
        yield  # pragma: no cover - unreachable, and that is the point

    with patch.object(BabyLogBookClient, "async_events", _removed):
        await coordinator._async_stream()

    assert coordinator.update_interval is None
    assert issue_present(hass, ISSUE_MEMBER_REMOVED, entry) is not None


async def test_the_stream_waits_out_a_lapsed_household(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Nothing changes while it lasts, so nothing keeps reconnecting."""
    mock_state(aioclient_mock)
    assert await setup_entry(hass, entry, aioclient_mock)
    coordinator = entry.runtime_data

    async def _lapsed(_self: object) -> AsyncIterator[str]:
        coordinator._stopped = True
        raise Lapsed("paused")
        yield  # pragma: no cover - unreachable, and that is the point

    with patch.object(BabyLogBookClient, "async_events", _lapsed):
        await coordinator._async_stream()

    assert not coordinator._stream_allowed.is_set()
    assert issue_present(hass, ISSUE_HOSTING_PAUSED, entry) is not None
