"""The way in: one pasted Claim Link, and one error taxonomy behind it.

A Parent sends a Claim Link over WhatsApp; the user pastes the whole URL into
one field and the panel is bound to the Household. Looking never spends the
link, so the flow previews first and claims on confirm.

Every failure maps to **exactly one** Home Assistant idiom, and the point of
that is that nobody invents a fourth: every pre-claim failure is a form error,
so the user re-pastes rather than starting over, and aborts are reserved for
identity outcomes.

Re-auth is the same step with the same field and the same error rows — one code
path, two entry points. What it asks for is a **Rescue Link** a Parent mints
from Settings, in the same words as the lost phone.
"""

from __future__ import annotations

import ipaddress
import logging
import uuid
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs, urlparse

import voluptuous as vol
from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    BabyLogBookClient,
    CannotConnect,
    IncompatibleResponse,
    Lapsed,
    LinkPreview,
    LinkRefused,
    NotBabyLogBook,
    Removed,
    Unauthenticated,
    server_is_too_old,
)
from .const import (
    CONF_CLAIM_LINK,
    CONF_DEVICE_ID,
    CONF_HOUSEHOLD_ID,
    CONF_HOUSEHOLD_NAME,
    CONF_MEMBER_ID,
    CONF_ORIGIN,
    CONF_SESSION,
    DOMAIN,
    MIN_SERVER_VERSION,
)

_LOGGER = logging.getLogger(__name__)

STEP_SCHEMA = vol.Schema({vol.Required(CONF_CLAIM_LINK): str})

#: Every reason the server has for refusing a link, and the one form error each
#: of them lands on. Anything else is Home Assistant's own `unknown`.
_LINK_ERRORS = {
    "expired": "link_expired",
    "used": "link_used",
    "burnt": "link_burnt",
    "unknown": "link_unknown",
}


class BabyLogBookConfigFlow(ConfigFlow, domain=DOMAIN):
    """Claim a Claim Link, once at setup and again whenever the session goes."""

    VERSION = 1

    def __init__(self) -> None:
        """Nothing is known until something is pasted."""
        self._origin: str = ""
        self._token: str = ""
        self._preview: LinkPreview | None = None

    # --- setup -----------------------------------------------------------

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Take the pasted link and say what it is for."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}

        if user_input is not None:
            parsed = _parse_claim_link(user_input[CONF_CLAIM_LINK])
            if parsed is None:
                errors["base"] = "link_unknown"
            elif not _origin_is_safe(parsed[0]):
                # The flow checks, because a server behind a proxy cannot
                # reliably see its own scheme. Private hosts stay exempt, so
                # self-hosters and the dev env are never blocked.
                errors["base"] = "http_public_origin"
            else:
                self._origin, self._token = parsed
                client = self._client()
                try:
                    preview = await client.async_preview(self._token)
                except LinkRefused as err:
                    errors["base"] = _LINK_ERRORS.get(err.reason, "unknown")
                except Lapsed:
                    errors["base"] = "hosting_paused"
                except NotBabyLogBook:
                    errors["base"] = "not_baby_log_book"
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except (Unauthenticated, Removed, IncompatibleResponse):
                    errors["base"] = "unknown"
                else:
                    if server_is_too_old(preview.app_version):
                        errors["base"] = "server_too_old"
                        placeholders = {
                            "minimum": MIN_SERVER_VERSION,
                            "server": preview.app_version or "?",
                        }
                    else:
                        self._preview = preview
                        return await self.async_step_confirm()

        return self.async_show_form(
            step_id=self._step,
            data_schema=STEP_SCHEMA,
            errors=errors,
            description_placeholders=placeholders or None,
        )

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show what was found, then spend the link on confirm."""
        assert self._preview is not None

        if user_input is None:
            return self.async_show_form(
                step_id="confirm",
                data_schema=vol.Schema({}),
                description_placeholders={
                    "origin": self._origin,
                    "name": self._preview.display_name or "",
                },
            )

        client = self._client()
        device_id = self._device_id()
        try:
            claimed = await client.async_claim(
                self._token, device_id, self.hass.config.time_zone or "UTC"
            )
        except LinkRefused as err:
            return await self._async_back(_LINK_ERRORS.get(err.reason, "unknown"))
        except Lapsed:
            return await self._async_back("hosting_paused")
        except NotBabyLogBook:
            return await self._async_back("not_baby_log_book")
        except CannotConnect:
            return await self._async_back("cannot_connect")

        data = {
            CONF_ORIGIN: self._origin,
            CONF_SESSION: claimed.session,
            CONF_MEMBER_ID: claimed.member_id,
            CONF_HOUSEHOLD_ID: claimed.household_id,
            CONF_HOUSEHOLD_NAME: claimed.household_name,
            CONF_DEVICE_ID: device_id,
        }

        if self.source == SOURCE_REAUTH:
            entry = self._get_reauth_entry()
            if (
                claimed.member_id != entry.data[CONF_MEMBER_ID]
                or claimed.household_id != entry.data[CONF_HOUSEHOLD_ID]
            ):
                # The link is spent either way — the preview is deliberately
                # thin and carries no Member — but nothing stays bound wrong.
                await client.async_discard_session()
                return self.async_abort(
                    reason="wrong_member",
                    description_placeholders={"name": self._preview.display_name or "?"},
                )
            return self.async_update_reload_and_abort(entry, data_updates=data)

        # The Household is the identity: a second wall panel is a second Home
        # Assistant, not a second entry.
        await self.async_set_unique_id(claimed.household_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=claimed.household_name, data=data)

    # --- re-auth ---------------------------------------------------------

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The session went stale; ask for a Rescue Link."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Same field, same error rows, one code path."""
        return await self.async_step_user(user_input)

    # --- plumbing --------------------------------------------------------

    @property
    def _step(self) -> str:
        """The step whose strings the one field is wearing right now.

        Setup and re-auth are one code path with two entry points, and this is
        the only place that has to know which of the two it is in.
        """
        return "reauth_confirm" if self.source == SOURCE_REAUTH else "user"

    def _client(self) -> BabyLogBookClient:
        return BabyLogBookClient(async_get_clientsession(self.hass), self._origin)

    def _device_id(self) -> str:
        """Re-bind the Device this panel already is, or mint one."""
        if self.source == SOURCE_REAUTH:
            existing = self._get_reauth_entry().data.get(CONF_DEVICE_ID)
            if isinstance(existing, str) and existing:
                return existing
        return uuid.uuid4().hex

    async def _async_back(self, error: str) -> ConfigFlowResult:
        """The link went bad between looking and claiming: re-paste."""
        self._preview = None
        return self.async_show_form(
            step_id=self._step,
            data_schema=STEP_SCHEMA,
            errors={"base": error},
        )


def _parse_claim_link(pasted: str) -> tuple[str, str] | None:
    """Split the pasted URL into an origin and a token, or refuse it."""
    try:
        url = urlparse(pasted.strip())
    except ValueError:
        return None
    if url.scheme not in ("http", "https") or not url.hostname:
        return None
    token = (parse_qs(url.query).get("t") or [""])[0]
    if not token:
        return None
    return f"{url.scheme}://{url.netloc}", token


def _origin_is_safe(origin: str) -> bool:
    """Plain HTTP is refused against public hosts, and only those.

    Loopback, the RFC1918 ranges, `.local` and `.internal` stay exempt: a
    self-hosted Baby Log Book on a home network has no certificate to offer,
    and refusing it would block the people this integration is for.
    """
    url = urlparse(origin)
    if url.scheme == "https":
        return True
    host = (url.hostname or "").lower()
    if host.endswith((".local", ".internal", ".localhost")):
        return True
    if "." not in host:
        # A single-label name — `localhost`, `nas`, `planetmobile` — cannot be
        # a public DNS name, and it is what a home network actually calls its
        # machines.
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local
