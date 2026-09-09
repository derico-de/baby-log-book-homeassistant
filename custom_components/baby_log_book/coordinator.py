"""One coordinator holding the Household's current state.

The stream is the wake signal and the poll is the fallback, which is Home
Assistant's own push-plus-poll idiom (the Withings pattern: flip
``update_interval`` as the listener connects and disconnects). The wake carries
no data, so it triggers a **conditional** read rather than delivering one.

The write half lives here too, because the outbox and the read share a
lifecycle: a press mints its revision id immediately, the batch goes down the
one write path there is, and a retry after a lost response is a no-op because
push is insert-only.
"""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    HomeAssistantError,
)
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    BabyLogBookClient,
    BabyLogBookError,
    HubState,
    IncompatibleResponse,
    Lapsed,
    Removed,
    Unauthenticated,
    WriteRefused,
    server_is_too_old,
)
from .const import (
    BACKOFF_BASE_S,
    BACKOFF_CAP_S,
    CONF_DEVICE_ID,
    CONF_HOUSEHOLD_ID,
    CONF_HOUSEHOLD_NAME,
    CONF_MEMBER_ID,
    DOMAIN,
    ISSUE_HOSTING_PAUSED,
    ISSUE_INTEGRATION_OUTDATED,
    MIN_SERVER_VERSION,
    OUTBOX_LIMIT,
    POLL_LAPSED,
    POLL_STREAM_DOWN,
    POLL_STREAM_HEALTHY,
    WAKE_DEBOUNCE_S,
)
from .issues import (
    async_clear,
    async_hosting_paused,
    async_integration_outdated,
    async_member_removed,
)

_LOGGER = logging.getLogger(__name__)

type BabyLogBookConfigEntry = ConfigEntry[BabyLogBookCoordinator]


class BabyLogBookCoordinator(DataUpdateCoordinator[HubState]):
    """The Household's live picture, and the queue of what the wall wrote."""

    config_entry: BabyLogBookConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: BabyLogBookConfigEntry,
        client: BabyLogBookClient,
    ) -> None:
        """Wire the coordinator to one config entry.

        ``config_entry`` is passed explicitly: the implicit context-variable
        fallback is deprecated and is being removed.
        """
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            # Until the stream says hello we are, by definition, polling.
            update_interval=POLL_STREAM_DOWN,
            request_refresh_debouncer=Debouncer(
                hass, _LOGGER, cooldown=WAKE_DEBOUNCE_S, immediate=False
            ),
        )
        self.client = client
        self.household_id: str = entry.data[CONF_HOUSEHOLD_ID]
        self.household_name: str = entry.data.get(CONF_HOUSEHOLD_NAME) or entry.title
        self.member_id: str = entry.data[CONF_MEMBER_ID]
        self.device_id: str = entry.data[CONF_DEVICE_ID]
        #: What a press queued and the server has not taken yet.
        self.outbox: list[dict[str, Any]] = []
        #: When we last heard the server — a not-modified counts, because it is
        #: an answer. This is the staleness tell availability cannot express.
        self.last_heard: datetime | None = None
        self._etag: str | None = None
        self._lapsed = False
        self._stopped = False
        self._stream_allowed = asyncio.Event()
        self._stream_allowed.set()
        self._flush_lock = asyncio.Lock()

    # --- the read --------------------------------------------------------

    @property
    def _at_setup(self) -> bool:
        """Whether this read is the one the config entry is waiting on.

        The two terminal conditions are permanent errors at setup and ordinary
        update failures at runtime, and this is the difference between them.
        """
        return self.config_entry.state is ConfigEntryState.SETUP_IN_PROGRESS

    def _failed(self, message: str) -> Exception:
        """`ConfigEntryError` at setup — no retry — and `UpdateFailed` after."""
        if self._at_setup:
            return ConfigEntryError(message)
        return UpdateFailed(message)

    async def _async_update_data(self) -> HubState:
        """One conditional read, with whatever the wall wrote sent first."""
        await self._async_flush()

        try:
            state = await self.client.async_state(self._etag)
        except Unauthenticated as err:
            # A stale session opens re-auth, which asks for a Rescue Link.
            raise ConfigEntryAuthFailed("the Hub has been signed out") from err
        except Removed as err:
            self._async_stop_for_removal()
            raise self._failed("this Hub's Member has been removed") from err
        except Lapsed as err:
            self._async_enter_lapsed()
            raise self._failed("hosting is paused for this Household") from err
        except IncompatibleResponse as err:
            async_integration_outdated(self.hass, self.config_entry.entry_id)
            raise UpdateFailed(f"this integration cannot read the server: {err}") from err
        except BabyLogBookError as err:
            # A network failure at setup is the framework's own not-ready
            # retry, never a loop written here.
            raise UpdateFailed(str(err)) from err

        # The dual gate's second half: every setup and every restart re-checks,
        # and there is deliberately no per-response check at runtime — a server
        # rolled back mid-flight is an operator act, and it surfaces here at the
        # next reload.
        if state is not None and self._at_setup and server_is_too_old(state.app_version):
            raise ConfigEntryError(
                f"this deployment runs Baby Log Book {state.app_version}, "
                f"and this integration needs {MIN_SERVER_VERSION} or newer"
            )

        self._async_leave_lapsed()
        async_clear(self.hass, ISSUE_INTEGRATION_OUTDATED, self.config_entry.entry_id)
        self.last_heard = dt_util.utcnow()

        if state is None:
            # Nothing changed: the previous payload still stands, and this is a
            # successful update like any other.
            if self.data is None:  # pragma: no cover - we send no ETag we have no data for
                raise UpdateFailed("not-modified with nothing to hold on to")
            return self.data

        self._etag = state.etag
        return state

    # --- the wake signal -------------------------------------------------

    async def async_listen(self) -> None:
        """Hold the stream open for as long as the entry is loaded."""
        self.config_entry.async_create_background_task(
            self.hass, self._async_stream(), f"{DOMAIN} live stream"
        )

    async def _async_stream(self) -> None:
        """Reconnect for ever, with exponential backoff and full jitter.

        Full jitter rather than a plain doubling because a deploy must not
        bring the fleet back in one second.
        """
        attempt = 0
        while not self._stopped:
            await self._stream_allowed.wait()
            try:
                async for event in self.client.async_events():
                    if event == "hello":
                        attempt = 0
                        self._async_stream_up()
                    elif event == "wake":
                        await self.async_request_refresh()
            except Removed:
                self._async_stop_for_removal()
            except Lapsed:
                self._async_enter_lapsed()
            except BabyLogBookError as err:
                _LOGGER.debug("the live stream dropped: %s", err)
            self._async_stream_down()
            if self._stopped:
                return
            await asyncio.sleep(_backoff(attempt))
            attempt += 1

    def _async_stream_up(self) -> None:
        """The stream is carrying us; the poll drops back to its safety net."""
        if not self._lapsed and self.update_interval != POLL_STREAM_HEALTHY:
            self.update_interval = POLL_STREAM_HEALTHY

    def _async_stream_down(self) -> None:
        """No stream: poll often enough that a wall is not visibly stale."""
        if self._stopped or self._lapsed:
            return
        if self.update_interval != POLL_STREAM_DOWN:
            self.update_interval = POLL_STREAM_DOWN

    # --- the two conditions that change the cadence -----------------------

    def _async_enter_lapsed(self) -> None:
        """Hosting is paused: say so, drop the stream, and poll gently.

        Five minutes, not the sixty seconds of an outage — nothing changes
        while a Household is Lapsed, and the entry stays exactly where it is.
        """
        self._stream_allowed.clear()
        self.update_interval = POLL_LAPSED
        if self._lapsed:
            return
        self._lapsed = True
        async_hosting_paused(self.hass, self.config_entry.entry_id, self.household_name)

    def _async_leave_lapsed(self) -> None:
        """The first good answer, and reactivation stays anticlimactic."""
        if not self._lapsed:
            return
        self._lapsed = False
        async_clear(self.hass, ISSUE_HOSTING_PAUSED, self.config_entry.entry_id)
        self.update_interval = POLL_STREAM_DOWN
        self._stream_allowed.set()

    def _async_stop_for_removal(self) -> None:
        """A full stop, and never a re-auth.

        Removal burns the Rescue Links a re-auth dialog would ask for, so the
        only way back is a new Invite and a new entry.
        """
        if self._stopped:
            return
        self._stopped = True
        self._stream_allowed.clear()
        self.update_interval = None
        async_member_removed(self.hass, self.config_entry.entry_id, self.household_name)

    # --- the write -------------------------------------------------------

    async def async_write(self, entity_id: str, fields: Mapping[str, Any]) -> None:
        """Queue one revision and try to send it at once.

        At the bound this **raises**, in the user's face, rather than queuing
        silently: a hub is not a phone, and silently queuing feeds for six
        hours is worse than saying it did not send.
        """
        if len(self.outbox) >= OUTBOX_LIMIT:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="outbox_full",
                translation_placeholders={"limit": str(OUTBOX_LIMIT)},
            )
        self.outbox.append(
            {
                "id": uuid.uuid4().hex,
                "household_id": self.household_id,
                "kind": "entry",
                "entity_id": entity_id,
                "fields": dict(fields),
                # Our clock corrected by the offset we last observed, so a Hub
                # that was cut off writes the same slightly-late revision a
                # phone would.
                "merge_at": self.client.merge_at(),
                "device_id": self.device_id,
                "author_id": self.member_id,
            }
        )
        self._async_notify()
        await self._async_flush()

    def baby_name(self, baby_id: str) -> str:
        """As the Household spelled her, and her id if it has not said yet."""
        data = self.data
        if data is None:
            return baby_id
        name = (data.babies.get(baby_id) or {}).get("name")
        return str(name) if name else baby_id

    @property
    def origin(self) -> str:
        """The deployment this Household lives on."""
        return self.client.origin

    def creation(self, baby_id: str, entry_type: str) -> dict[str, Any]:
        """The shared fields of any new Entry, as the app writes them.

        `recording_zone` is captured because it is unrecoverable later; nothing
        reads it. `occurred_at` is our clock corrected by the offset, because
        what a wall logs happened when it was pressed.
        """
        return {
            "baby_id": baby_id,
            "type": entry_type,
            "occurred_at": self.client.merge_at(),
            "ended_at": None,
            "recording_zone": self.hass.config.time_zone or "UTC",
            "note": None,
        }

    async def _async_flush(self) -> None:
        """Send what is queued, and keep whatever the server did not settle.

        A lost response is retried, which is safe because push is insert-only.
        A refusal is not: a revision the server has rejected never becomes
        acceptable, and retrying it for ever would block the fifty behind it.
        So the outbox lets go of exactly what came back settled — accepted or
        rejected — and holds everything else for the next try.
        """
        async with self._flush_lock:
            batch = list(self.outbox)
            if not batch or self._stopped:
                return
            try:
                result = await self.client.async_push(batch, self.device_id)
            except WriteRefused as err:
                # The whole batch was malformed, which is not a thing a later
                # attempt fixes either.
                _LOGGER.error("the server refused %d queued writes: %s", len(batch), err)
                settled = {revision["id"] for revision in batch}
            except BabyLogBookError as err:
                _LOGGER.debug("could not send %d queued writes: %s", len(batch), err)
                return
            else:
                settled = set(result.settled)
                if result.rejected:
                    _LOGGER.error(
                        "the server rejected %d of %d queued writes",
                        len(result.rejected),
                        len(batch),
                    )
            self.outbox = [r for r in self.outbox if r["id"] not in settled]
        self._async_notify()

    def _async_notify(self) -> None:
        """Tell the pending-writes sensor, once there is anybody to tell."""
        if self.data is not None:
            self.async_update_listeners()


def _backoff(attempt: int) -> float:
    """Exponential from five seconds, capped at five minutes, full jitter."""
    ceiling = min(BACKOFF_CAP_S, BACKOFF_BASE_S * 2 ** min(attempt, 10))
    return random.uniform(0, ceiling)
