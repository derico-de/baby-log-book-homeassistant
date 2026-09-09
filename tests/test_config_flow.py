"""One pasted Claim Link, and every way it can fail.

Every row of the claim-time table in the specification has a test here, because
the point of that table is that nobody invents a fourth idiom.
"""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.baby_log_book.const import (
    CONF_CLAIM_LINK,
    CONF_HOUSEHOLD_ID,
    CONF_MEMBER_ID,
    CONF_SESSION,
    DOMAIN,
)

from .conftest import (
    HOUSEHOLD_ID,
    ORIGIN,
    SERVER_VERSION,
    mock_state,
    mock_stream_endpoint,
)

LINK = f"{ORIGIN}/claim?t=tok123"
VERSION_BLOCK = {
    "protocol_version": 2,
    "app_version": SERVER_VERSION,
    "git_sha": "abc1234",
    "source": "test",
    "server_time": 1_724_800_000_000,
}


def mock_preview(mocker: AiohttpClientMocker, **body: Any) -> None:
    """What looking at the link says."""
    payload = {"ok": True, "kind": "invite", "display_name": "Home Assistant", **VERSION_BLOCK}
    payload.update(body)
    mocker.get(f"{ORIGIN}/api/claim", json=payload)


def mock_claim(mocker: AiohttpClientMocker, member_id: str = "m-hub", **body: Any) -> None:
    """What spending it says, cookie and all."""
    payload: dict[str, Any] = {
        "ok": True,
        "kind": "invite",
        "member_id": member_id,
        "household": {
            "id": HOUSEHOLD_ID,
            "name": "Zuhause",
            "day_start": "05:00",
            "zone": "Europe/Berlin",
        },
        **VERSION_BLOCK,
    }
    payload.update(body)
    mocker.post(
        f"{ORIGIN}/api/claim",
        json=payload,
        headers={"Set-Cookie": "blb_session=fresh-token; Path=/; HttpOnly"},
    )


async def paste(hass: HomeAssistant, link: str = LINK) -> ConfigFlowResult:
    """Start the flow and paste one link."""
    started = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    return await hass.config_entries.flow.async_configure(
        started["flow_id"], {CONF_CLAIM_LINK: link}
    )


async def test_the_way_in(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """Paste, look, confirm, claimed."""
    mock_preview(aioclient_mock)
    mock_claim(aioclient_mock)

    looked = await paste(hass)
    assert looked["type"] is FlowResultType.FORM
    assert looked["step_id"] == "confirm"
    assert (looked["description_placeholders"] or {})["origin"] == ORIGIN

    done = await hass.config_entries.flow.async_configure(looked["flow_id"], {})
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert done["title"] == "Zuhause"
    assert done["result"].unique_id == HOUSEHOLD_ID
    assert done["data"][CONF_SESSION] == "fresh-token"
    assert done["data"][CONF_MEMBER_ID] == "m-hub"


async def test_looking_never_spends_the_link(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The preview is a GET, and no claim is posted until confirm."""
    mock_preview(aioclient_mock)
    await paste(hass)
    assert [call[0] for call in aioclient_mock.mock_calls] == ["GET"]


@pytest.mark.parametrize(
    ("reason", "error"),
    [
        ("expired", "link_expired"),
        ("used", "link_used"),
        ("burnt", "link_burnt"),
        ("unknown", "link_unknown"),
        ("rate_limited", "unknown"),
    ],
)
async def test_a_refused_link_is_a_form_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, reason: str, error: str
) -> None:
    """So the user re-pastes rather than starting over."""
    mock_preview(aioclient_mock, ok=False, reason=reason)
    result = await paste(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": error}


async def test_a_url_that_is_not_a_claim_link(hass: HomeAssistant) -> None:
    """No token, no link — and nothing is fetched to find that out."""
    result = await paste(hass, f"{ORIGIN}/settings")
    assert result["errors"] == {"base": "link_unknown"}


async def test_an_unreachable_origin(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Home Assistant's own key for this."""
    aioclient_mock.get(f"{ORIGIN}/api/claim", exc=TimeoutError())
    result = await paste(hass)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_something_that_is_not_a_baby_log_book(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """It answered, but not like our API."""
    aioclient_mock.get(f"{ORIGIN}/api/claim", status=404, text="Not found")
    result = await paste(hass)
    assert result["errors"] == {"base": "not_baby_log_book"}


async def test_something_that_answers_json_but_not_ours(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """No version block, so it is not a deployment of ours."""
    aioclient_mock.get(f"{ORIGIN}/api/claim", json={"hello": "world"})
    result = await paste(hass)
    assert result["errors"] == {"base": "not_baby_log_book"}


async def test_plain_http_against_a_public_host(hass: HomeAssistant) -> None:
    """The flow checks, because a server behind a proxy cannot see its scheme."""
    result = await paste(hass, "http://babylog.example/claim?t=tok123")
    assert result["errors"] == {"base": "http_public_origin"}


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://192.168.1.20:5173",
        "http://babylog.local",
        "http://host.docker.internal:5173",
        "http://planetmobile:5173",
    ],
)
async def test_plain_http_stays_allowed_at_home(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, origin: str
) -> None:
    """Self-hosters and the dev env are never blocked by this rule."""
    aioclient_mock.get(
        f"{origin}/api/claim", json={"ok": False, "reason": "unknown", **VERSION_BLOCK}
    )
    result = await paste(hass, f"{origin}/claim?t=tok123")
    assert result["errors"] == {"base": "link_unknown"}


async def test_a_lapsed_household(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """Checked before the link is spent; a repair issue cannot be the surface."""
    aioclient_mock.get(f"{ORIGIN}/api/claim", status=402, json={"code": "lapsed", **VERSION_BLOCK})
    result = await paste(hass)
    assert result["errors"] == {"base": "hosting_paused"}


async def test_a_server_too_old(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """The claim-time half of the dual gate, carrying both numbers."""
    mock_preview(aioclient_mock, app_version="1.24.0")
    result = await paste(hass)
    assert result["errors"] == {"base": "server_too_old"}
    assert result["description_placeholders"] == {"minimum": "1.25.0", "server": "1.24.0"}


async def test_a_household_already_configured(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A second wall panel is a second Home Assistant, not a second entry."""
    entry.add_to_hass(hass)
    mock_preview(aioclient_mock)
    mock_claim(aioclient_mock)

    looked = await paste(hass)
    done = await hass.config_entries.flow.async_configure(looked["flow_id"], {})
    assert done["type"] is FlowResultType.ABORT
    assert done["reason"] == "already_configured"


async def test_a_link_that_goes_bad_between_looking_and_claiming(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Somebody else claimed it while the confirm form was on screen."""
    mock_preview(aioclient_mock)
    aioclient_mock.post(f"{ORIGIN}/api/claim", status=400, json={"ok": False, "reason": "used"})

    looked = await paste(hass)
    done = await hass.config_entries.flow.async_configure(looked["flow_id"], {})
    assert done["type"] is FlowResultType.FORM
    assert done["errors"] == {"base": "link_used"}


async def test_a_rescue_link_is_accepted_at_setup_too(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Kind is never enforced; identity is."""
    mock_preview(aioclient_mock, kind="rescue", display_name="Home Assistant")
    mock_claim(aioclient_mock, kind="rescue")

    looked = await paste(hass)
    done = await hass.config_entries.flow.async_configure(looked["flow_id"], {})
    assert done["type"] is FlowResultType.CREATE_ENTRY


# --- re-auth -------------------------------------------------------------


async def test_reauth_rebinds_the_same_member(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Same field, same error rows, and the entry keeps its identity."""
    entry.add_to_hass(hass)
    mock_preview(aioclient_mock, kind="rescue")
    mock_claim(aioclient_mock, kind="rescue")
    mock_state(aioclient_mock)
    mock_stream_endpoint(aioclient_mock)

    started = await entry.start_reauth_flow(hass)
    assert started["step_id"] == "reauth_confirm"

    looked = await hass.config_entries.flow.async_configure(
        started["flow_id"], {CONF_CLAIM_LINK: LINK}
    )
    assert looked["step_id"] == "confirm"

    done = await hass.config_entries.flow.async_configure(looked["flow_id"], {})
    assert done["type"] is FlowResultType.ABORT
    assert done["reason"] == "reauth_successful"
    assert entry.data[CONF_SESSION] == "fresh-token"


async def test_reauth_with_the_wrong_member_discards_the_session_first(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """The link is spent either way, but nothing stays bound wrong."""
    entry.add_to_hass(hass)
    mock_preview(aioclient_mock, kind="rescue", display_name="Oma")
    mock_claim(aioclient_mock, member_id="m-oma", kind="rescue")
    aioclient_mock.delete(f"{ORIGIN}/api/session", json={"ok": True})

    started = await entry.start_reauth_flow(hass)
    looked = await hass.config_entries.flow.async_configure(
        started["flow_id"], {CONF_CLAIM_LINK: LINK}
    )
    done = await hass.config_entries.flow.async_configure(looked["flow_id"], {})

    assert done["type"] is FlowResultType.ABORT
    assert done["reason"] == "wrong_member"
    assert done["description_placeholders"] == {"name": "Oma"}
    assert ("DELETE", "/api/session") in [
        (call[0], call[1].path) for call in aioclient_mock.mock_calls
    ]
    # The entry is untouched: it is still bound to the Member it always was.
    assert entry.data[CONF_SESSION] == "session-token"
    assert entry.data[CONF_MEMBER_ID] == "m-hub"


async def test_reauth_into_another_household_is_the_wrong_member_too(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Identity is the Household as much as the Member."""
    entry.add_to_hass(hass)
    mock_preview(aioclient_mock, kind="rescue")
    mock_claim(aioclient_mock, household={"id": "h2", "name": "Anderswo"})
    aioclient_mock.delete(f"{ORIGIN}/api/session", json={"ok": True})

    started = await entry.start_reauth_flow(hass)
    looked = await hass.config_entries.flow.async_configure(
        started["flow_id"], {CONF_CLAIM_LINK: LINK}
    )
    done = await hass.config_entries.flow.async_configure(looked["flow_id"], {})
    assert done["reason"] == "wrong_member"
    assert entry.data[CONF_HOUSEHOLD_ID] == HOUSEHOLD_ID


async def test_reauth_keeps_the_device_it_already_was(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A re-bind is the same panel, so it re-binds the same Device."""
    entry.add_to_hass(hass)
    mock_preview(aioclient_mock, kind="rescue")
    mock_claim(aioclient_mock, kind="rescue")
    mock_state(aioclient_mock)
    mock_stream_endpoint(aioclient_mock)

    started = await entry.start_reauth_flow(hass)
    looked = await hass.config_entries.flow.async_configure(
        started["flow_id"], {CONF_CLAIM_LINK: LINK}
    )
    await hass.config_entries.flow.async_configure(looked["flow_id"], {})

    posted = [call for call in aioclient_mock.mock_calls if call[0] == "POST"]
    assert posted[0][2]["device_id"] == "dev-hub"


async def test_a_url_that_does_not_parse(hass: HomeAssistant) -> None:
    """A mangled paste is refused before anything is fetched."""
    result = await paste(hass, "https://[not-an-address/claim?t=tok")
    assert result["errors"] == {"base": "link_unknown"}


async def test_a_preview_that_answers_something_startling(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Nothing about a Claim Link should ever be a 401; say so honestly."""
    aioclient_mock.get(f"{ORIGIN}/api/claim", status=401, json={"code": "unauthenticated"})
    result = await paste(hass)
    assert result["errors"] == {"base": "unknown"}


async def test_the_server_going_out_between_looking_and_claiming(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Re-paste, once it is back: the link has not been spent."""
    mock_preview(aioclient_mock)
    aioclient_mock.post(f"{ORIGIN}/api/claim", exc=TimeoutError())

    looked = await paste(hass)
    done = await hass.config_entries.flow.async_configure(looked["flow_id"], {})
    assert done["type"] is FlowResultType.FORM
    assert done["errors"] == {"base": "cannot_connect"}


async def test_hosting_that_pauses_between_looking_and_claiming(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A repair issue cannot be the surface: there is no entry yet."""
    mock_preview(aioclient_mock)
    aioclient_mock.post(f"{ORIGIN}/api/claim", status=402, json={"code": "lapsed"})

    looked = await paste(hass)
    done = await hass.config_entries.flow.async_configure(looked["flow_id"], {})
    assert done["errors"] == {"base": "hosting_paused"}


async def test_a_claim_that_answers_nonsense(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Something changed underneath us; the form comes back."""
    mock_preview(aioclient_mock)
    aioclient_mock.post(f"{ORIGIN}/api/claim", json={"ok": True})

    looked = await paste(hass)
    done = await hass.config_entries.flow.async_configure(looked["flow_id"], {})
    assert done["errors"] == {"base": "not_baby_log_book"}
