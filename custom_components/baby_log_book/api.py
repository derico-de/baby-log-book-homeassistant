"""The three calls a Hub makes, and nothing else.

A Hub is an ordinary Member with an ordinary session (ADR-0034). It reads one
derived endpoint that ships no rows, it writes plain revisions down the one
write path there is, and it listens to a stream that carries a wake signal and
never data. It never pulls, and it never receives a Revision.

Two things this module owns because nothing else can:

- **The ETag.** The last one is echoed back verbatim in ``If-None-Match`` and
  is **never parsed** — the format is the server's freedom, and reading it here
  would freeze it there.
- **The clock offset.** Recomputed from ``server_time`` on every non-304
  answer, reads and writes alike, and applied to every merge key we mint. A Hub
  that was cut off writes the same slightly-late revision a phone would.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from http.cookies import SimpleCookie
from types import MappingProxyType
from typing import Any, Final, Self

import aiohttp
from awesomeversion import AwesomeVersion, AwesomeVersionException

from .const import MIN_SERVER_VERSION, SESSION_COOKIE

_LOGGER = logging.getLogger(__name__)

#: Long enough for a small deployment on a slow link, short enough that a
#: config flow does not look hung.
REQUEST_TIMEOUT: Final = aiohttp.ClientTimeout(total=15)
#: The stream is meant to stay open forever, so there is no total timeout — but
#: the server sends a keepalive comment every 25 seconds, so silence past a
#: minute means the connection is dead rather than quiet.
STREAM_TIMEOUT: Final = aiohttp.ClientTimeout(total=None, sock_read=60)

PATH_CLAIM: Final = "/api/claim"
PATH_SESSION: Final = "/api/session"
PATH_STATE: Final = "/api/hub/state"
PATH_LIVE: Final = "/api/sync/live"
PATH_PUSH: Final = "/api/sync/push"


class BabyLogBookError(Exception):
    """Anything this client could not do."""


class CannotConnect(BabyLogBookError):
    """The origin did not answer: DNS, a timeout, a refused connection."""


class NotBabyLogBook(BabyLogBookError):
    """Something answered, but it does not answer like a Baby Log Book."""


class Unauthenticated(BabyLogBookError):
    """The session proof is stale. A fresh Claim Link is the way back."""


class Removed(BabyLogBookError):
    """The Member has been Removed. There is no way back to this entry."""


class Lapsed(BabyLogBookError):
    """The Household's hosting is paused. A billing state, not a defect."""


class LinkRefused(BabyLogBookError):
    """The link cannot be used: unknown, expired, used, burnt, rate limited."""

    def __init__(self, reason: str) -> None:
        """Remember which of them it was; the flow maps it to a form error."""
        super().__init__(reason)
        self.reason = reason


class IncompatibleResponse(BabyLogBookError):
    """A good answer this release cannot read — so this release is the old half.

    Rare by construction: a wire change lands server-side first and
    backward-compatibly (ADR-0039). When it happens anyway, the honest thing to
    say is *update the Baby Log Book integration*, which is the third and last
    repair issue.
    """


class WriteRefused(BabyLogBookError):
    """The server would not take a revision. Never a reason to retry it."""


@dataclass(frozen=True, slots=True)
class LinkPreview:
    """What looking at a Claim Link says, without spending it."""

    kind: str
    display_name: str | None
    app_version: str


@dataclass(frozen=True, slots=True)
class ClaimResult:
    """What a spent Claim Link left behind."""

    session: str
    member_id: str
    household_id: str
    household_name: str
    app_version: str


@dataclass(frozen=True, slots=True)
class PushResult:
    """What the server did with a batch: every id it settled, either way."""

    accepted: frozenset[str]
    #: Never worth retrying — a refusal is not a lost response.
    rejected: frozenset[str]

    @property
    def settled(self) -> frozenset[str]:
        """Everything the server accounted for, and nothing else."""
        return self.accepted | self.rejected


@dataclass(frozen=True, slots=True)
class HubState:
    """The Household as a wall reads it.

    ``babies`` is keyed by Baby id and holds each payload verbatim: the field
    names are the entity keys, so nothing in here renames anything.
    """

    cursor: int
    household: Mapping[str, Any]
    babies: Mapping[str, Mapping[str, Any]]
    app_version: str
    etag: str | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], etag: str | None) -> Self:
        """Read one answer from ``GET /api/hub/state``."""
        babies: dict[str, Mapping[str, Any]] = {}
        for baby in payload.get("babies") or []:
            if isinstance(baby, Mapping) and isinstance(baby.get("id"), str):
                babies[baby["id"]] = MappingProxyType(dict(baby))
        household = payload.get("household")
        if not isinstance(household, Mapping) or not household.get("id"):
            raise IncompatibleResponse("the state payload names no Household")
        return cls(
            cursor=int(payload.get("cursor") or 0),
            household=MappingProxyType(dict(household)),
            babies=MappingProxyType(babies),
            app_version=str(payload.get("app_version") or ""),
            etag=etag,
        )


def server_is_too_old(app_version: str) -> bool:
    """Whether this release refuses to talk to that one (ADR-0039, §7.1).

    An unparseable version is **not** too old: a deployment built from a branch
    reports whatever its package says, and refusing to run against it would
    make this gate a nuisance rather than a contract.
    """
    try:
        return AwesomeVersion(app_version) < AwesomeVersion(MIN_SERVER_VERSION)
    except (AwesomeVersionException, ValueError):
        return False


@dataclass(slots=True)
class BabyLogBookClient:
    """One session against one deployment."""

    session: aiohttp.ClientSession
    origin: str
    cookie: str | None = None
    #: ``server_time − our clock``, in milliseconds.
    offset_ms: int = 0

    def __post_init__(self) -> None:
        """Normalise the origin, so every URL below is one join away."""
        self.origin = self.origin.rstrip("/")

    # --- the merge key ---------------------------------------------------

    def merge_at(self) -> int:
        """Our clock corrected by the offset we last observed."""
        return int(time.time() * 1000) + self.offset_ms

    def _observe(self, payload: Mapping[str, Any]) -> None:
        """Take the clock offset off any non-304 answer."""
        server_time = payload.get("server_time")
        if isinstance(server_time, int):
            self.offset_ms = server_time - int(time.time() * 1000)

    # --- plumbing --------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {"accept": "application/json"}
        if self.cookie:
            headers["cookie"] = f"{SESSION_COOKIE}={self.cookie}"
        return headers

    @staticmethod
    def _raise_for_status(response: aiohttp.ClientResponse) -> None:
        """One status per flow, so nothing has to read a body to know which."""
        if response.status == 401:
            raise Unauthenticated("the session proof is stale")
        if response.status == 403:
            raise Removed("the Member has been Removed")
        if response.status == 402:
            raise Lapsed("hosting is paused")
        if response.status == 404:
            raise NotBabyLogBook("no Baby Log Book at that address")
        if response.status >= 500:
            raise CannotConnect(f"the server answered {response.status}")

    @staticmethod
    async def _json(response: aiohttp.ClientResponse) -> dict[str, Any]:
        try:
            body = await response.json(content_type=None)
        except (aiohttp.ClientError, ValueError) as err:
            raise NotBabyLogBook("that address does not answer JSON") from err
        if not isinstance(body, dict):
            raise NotBabyLogBook("that address does not answer like our API")
        return body

    # --- looking, and claiming -------------------------------------------

    async def async_preview(self, token: str) -> LinkPreview:
        """What the link is for. Looking never spends it."""
        try:
            async with self.session.get(
                f"{self.origin}{PATH_CLAIM}",
                params={"t": token},
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
            ) as response:
                self._raise_for_status(response)
                body = await self._json(response)
        except (TimeoutError, aiohttp.ClientError) as err:
            raise CannotConnect(str(err)) from err

        if "app_version" not in body:
            raise NotBabyLogBook("that address does not answer like our API")
        self._observe(body)
        if not body.get("ok"):
            raise LinkRefused(str(body.get("reason") or "unknown"))
        return LinkPreview(
            kind=str(body.get("kind") or ""),
            display_name=body.get("display_name"),
            app_version=str(body.get("app_version") or ""),
        )

    async def async_claim(self, token: str, device_id: str, zone: str) -> ClaimResult:
        """Spend the link and hold the session it mints."""
        try:
            async with self.session.post(
                f"{self.origin}{PATH_CLAIM}",
                json={"token": token, "device_id": device_id, "zone": zone},
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status == 402:
                    raise Lapsed("hosting is paused")
                body = await self._json(response)
                cookie = _session_cookie(response)
        except (TimeoutError, aiohttp.ClientError) as err:
            raise CannotConnect(str(err)) from err

        self._observe(body)
        if not body.get("ok"):
            raise LinkRefused(str(body.get("reason") or "unknown"))
        household = body.get("household")
        if not isinstance(household, Mapping) or not cookie:
            raise NotBabyLogBook("the claim answered without a Household")
        self.cookie = cookie
        return ClaimResult(
            session=cookie,
            member_id=str(body.get("member_id") or ""),
            household_id=str(household.get("id") or ""),
            household_name=str(household.get("name") or ""),
            app_version=str(body.get("app_version") or ""),
        )

    async def async_discard_session(self) -> None:
        """Sign this Hub out again, best effort.

        Used when a claim during re-auth turned out to bind the wrong Member:
        the link is spent either way, but nothing stays bound wrong.
        """
        if not self.cookie:
            return
        try:
            async with self.session.delete(
                f"{self.origin}{PATH_SESSION}",
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
            ):
                pass
        except (TimeoutError, aiohttp.ClientError) as err:  # pragma: no cover - best effort
            _LOGGER.debug("could not discard the mis-claimed session: %s", err)
        finally:
            self.cookie = None

    # --- the read --------------------------------------------------------

    async def async_state(self, etag: str | None = None) -> HubState | None:
        """The Household's current state, or ``None`` for *nothing changed*."""
        headers = self._headers()
        if etag:
            headers["if-none-match"] = etag
        try:
            async with self.session.get(
                f"{self.origin}{PATH_STATE}", headers=headers, timeout=REQUEST_TIMEOUT
            ) as response:
                self._raise_for_status(response)
                if response.status == 304:
                    return None
                body = await self._json(response)
                fresh = response.headers.get("etag")
        except (TimeoutError, aiohttp.ClientError) as err:
            raise CannotConnect(str(err)) from err

        self._observe(body)
        return HubState.from_payload(body, fresh)

    # --- the write -------------------------------------------------------

    async def async_push(
        self, revisions: Sequence[Mapping[str, Any]], device_id: str
    ) -> PushResult:
        """Send a batch of plain revisions and say what became of them.

        Insert-only and client-minted, so a retry after a lost response is a
        no-op. ``protocol_version`` is deliberately not sent: that number is the
        phone's wire, which a Hub does not speak (§7.1).

        The answer names every revision it settled, so the caller lets go of
        exactly those and keeps anything the server did not account for.
        """
        try:
            async with self.session.post(
                f"{self.origin}{PATH_PUSH}",
                json={"device_id": device_id, "revisions": list(revisions)},
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
            ) as response:
                self._raise_for_status(response)
                if response.status >= 400:
                    raise WriteRefused(f"the server answered {response.status}")
                body = await self._json(response)
        except (TimeoutError, aiohttp.ClientError) as err:
            raise CannotConnect(str(err)) from err

        self._observe(body)
        return PushResult(
            accepted=_ids(body.get("accepted")),
            rejected=_ids(body.get("rejected")),
        )

    # --- the wake signal -------------------------------------------------

    async def async_events(self) -> AsyncIterator[str]:
        """Yield each event name, until the stream ends or fails.

        ``hello`` arrives as soon as the connection is up, which is what tells
        the coordinator to relax to the healthy poll floor; ``wake`` says
        *something changed* and carries no payload, so the coordinator answers
        with a conditional read.
        """
        try:
            async with self.session.get(
                f"{self.origin}{PATH_LIVE}",
                headers=self._headers() | {"accept": "text/event-stream"},
                timeout=STREAM_TIMEOUT,
            ) as response:
                self._raise_for_status(response)
                if response.status != 200:
                    raise CannotConnect(f"the stream answered {response.status}")
                async for raw in response.content:
                    line = raw.decode("utf-8", "replace").strip()
                    if line.startswith("event:"):
                        yield line.removeprefix("event:").strip()
        except (TimeoutError, aiohttp.ClientError) as err:
            raise CannotConnect(str(err)) from err


def _ids(value: object) -> frozenset[str]:
    """Read a list of revision ids off an answer, however it names them.

    `accepted` is a list of ids; `rejected` is a list of objects carrying one.
    Both are read the same way here, because the only question the outbox asks
    is *which of mine did you settle*.
    """
    if not isinstance(value, list):
        return frozenset()
    ids: set[str] = set()
    for item in value:
        if isinstance(item, str):
            ids.add(item)
        elif isinstance(item, Mapping) and isinstance(item.get("id"), str):
            ids.add(item["id"])
    return frozenset(ids)


def _session_cookie(response: aiohttp.ClientResponse) -> str | None:
    """Read the session out of ``Set-Cookie`` ourselves.

    Home Assistant's shared client session is not ours to keep credentials in,
    and the config entry is where Home Assistant stores every credential.
    """
    for header in response.headers.getall("Set-Cookie", []):
        jar = SimpleCookie()
        jar.load(header)
        if morsel := jar.get(SESSION_COOKIE):
            return morsel.value
    return None
