"""The client itself: the ETag, the clock, the cookie and the wake signal."""

from __future__ import annotations

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.baby_log_book.api import (
    BabyLogBookClient,
    CannotConnect,
    IncompatibleResponse,
    LinkRefused,
    NotBabyLogBook,
    Removed,
    Unauthenticated,
    WriteRefused,
    server_is_too_old,
)

from .conftest import ORIGIN, state_payload

pytestmark = pytest.mark.usefixtures("auto_enable_custom_integrations")


@pytest.fixture
def client(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> BabyLogBookClient:
    """A client against the mocked deployment, already holding a session."""
    return BabyLogBookClient(async_get_clientsession(hass), f"{ORIGIN}/", "session-token")


def test_a_version_nobody_can_parse_is_not_too_old() -> None:
    """A build from a branch is not a reason to refuse to run."""
    assert server_is_too_old("1.25.0")
    assert not server_is_too_old("1.26.0")
    assert not server_is_too_old("")
    assert not server_is_too_old("a-branch-build")


def test_the_origin_loses_its_trailing_slash(client: BabyLogBookClient) -> None:
    """So every path below is one join away."""
    assert client.origin == ORIGIN


async def test_a_body_that_is_not_json(
    client: BabyLogBookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A proxy's error page is not our API."""
    aioclient_mock.get(f"{ORIGIN}/api/claim", text="<html>hello</html>")
    with pytest.raises(NotBabyLogBook):
        await client.async_preview("tok")


async def test_a_body_that_is_json_but_not_an_object(
    client: BabyLogBookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Neither is a bare list."""
    aioclient_mock.get(f"{ORIGIN}/api/claim", json=[1, 2, 3])
    with pytest.raises(NotBabyLogBook):
        await client.async_preview("tok")


async def test_a_claim_that_mints_no_cookie(
    client: BabyLogBookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A claim without a session is not a claim."""
    aioclient_mock.post(f"{ORIGIN}/api/claim", json={"ok": True, "household": {"id": "h1"}})
    with pytest.raises(NotBabyLogBook):
        await client.async_claim("tok", "dev", "UTC")


async def test_a_claim_refused_for_a_reason(
    client: BabyLogBookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """The reason is carried through for the flow to map."""
    aioclient_mock.post(f"{ORIGIN}/api/claim", status=400, json={"ok": False, "reason": "burnt"})
    with pytest.raises(LinkRefused) as refused:
        await client.async_claim("tok", "dev", "UTC")
    assert refused.value.reason == "burnt"


async def test_a_claim_that_cannot_be_posted(
    client: BabyLogBookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A dropped connection is a connection problem, not a link problem."""
    aioclient_mock.post(f"{ORIGIN}/api/claim", exc=aiohttp.ClientError("boom"))
    with pytest.raises(CannotConnect):
        await client.async_claim("tok", "dev", "UTC")


async def test_discarding_a_session_we_never_had(client: BabyLogBookClient) -> None:
    """Nothing to sign out of, and nothing is called."""
    client.cookie = None
    await client.async_discard_session()


async def test_discarding_a_session_when_the_server_is_out(
    client: BabyLogBookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Best effort: the mis-claimed session is let go either way."""
    aioclient_mock.delete(f"{ORIGIN}/api/session", exc=TimeoutError())
    await client.async_discard_session()
    assert client.cookie is None


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, Unauthenticated),
        (403, Removed),
        (500, CannotConnect),
    ],
)
async def test_one_status_per_flow(
    client: BabyLogBookClient,
    aioclient_mock: AiohttpClientMocker,
    status: int,
    error: type[Exception],
) -> None:
    """Nothing has to read a body to know which flow it is in."""
    aioclient_mock.get(f"{ORIGIN}/api/hub/state", status=status, json={})
    with pytest.raises(error):
        await client.async_state()


async def test_a_state_answer_without_a_household(
    client: BabyLogBookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A good answer this release cannot read is the third repair issue."""
    aioclient_mock.get(f"{ORIGIN}/api/hub/state", json={"babies": []})
    with pytest.raises(IncompatibleResponse):
        await client.async_state()


async def test_a_baby_without_an_id_is_skipped(
    client: BabyLogBookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Something we cannot key is something we cannot stand an entity on."""
    payload = state_payload([{"name": "nameless"}])
    aioclient_mock.get(f"{ORIGIN}/api/hub/state", json=payload, headers={"etag": '"e"'})
    state = await client.async_state()
    assert state is not None
    assert state.babies == {}
    assert state.etag == '"e"'


async def test_the_state_read_can_simply_fail(
    client: BabyLogBookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A timeout is an outage, and the coordinator keeps its cadence."""
    aioclient_mock.get(f"{ORIGIN}/api/hub/state", exc=TimeoutError())
    with pytest.raises(CannotConnect):
        await client.async_state()


async def test_a_push_the_server_could_not_take(
    client: BabyLogBookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A malformed batch is never worth retrying."""
    aioclient_mock.post(f"{ORIGIN}/api/sync/push", status=400, json={"code": "malformed"})
    with pytest.raises(WriteRefused):
        await client.async_push([{"id": "r1"}], "dev")


async def test_a_push_that_never_arrived(
    client: BabyLogBookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Insert-only, so the retry after this is a no-op."""
    aioclient_mock.post(f"{ORIGIN}/api/sync/push", exc=TimeoutError())
    with pytest.raises(CannotConnect):
        await client.async_push([{"id": "r1"}], "dev")


async def test_a_push_updates_the_clock_offset(
    client: BabyLogBookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Every non-304 answer carries the clock, writes included."""
    aioclient_mock.post(
        f"{ORIGIN}/api/sync/push",
        json={"cursor": 8, "accepted": [], "rejected": [], "server_time": 4_000_000_000_000},
    )
    await client.async_push([{"id": "r1"}], "dev")
    assert client.offset_ms > 0


async def test_the_wake_signal_is_read_off_the_stream(
    client: BabyLogBookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Comments, retry hints and data lines are not events."""
    aioclient_mock.get(
        f"{ORIGIN}/api/sync/live",
        text="retry: 5000\n\nevent: hello\ndata: 1\n\n: keepalive\n\nevent: wake\ndata: 1\n\n",
    )
    assert [event async for event in client.async_events()] == ["hello", "wake"]


async def test_a_stream_that_will_not_open(
    client: BabyLogBookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """The coordinator backs off and tries again."""
    aioclient_mock.get(f"{ORIGIN}/api/sync/live", exc=aiohttp.ClientError("no"))
    with pytest.raises(CannotConnect):
        [event async for event in client.async_events()]


async def test_a_stream_that_answers_the_wrong_thing(
    client: BabyLogBookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A redirect to a login page is not a stream."""
    aioclient_mock.get(f"{ORIGIN}/api/sync/live", status=204, text="")
    with pytest.raises(CannotConnect):
        [event async for event in client.async_events()]
