"""Non-blocking Home Assistant and Supervisor client for Acoustica."""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from . import __version__

logger = logging.getLogger(__name__)

EVENT_STATE_UPDATE = "acoustica_state"
DISCOVERY_SERVICE = "acoustica"
PROTOCOL_VERSION = 1
DETECTOR_ID = "acoustica"

UrlOpen = Callable[..., Any]
Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class PendingState:
    """Versioned latest state for one detector profile."""

    sequence: int
    payload: dict[str, object]


class IntegrationClient:
    """Publish latest detector states without blocking the audio thread.

    The queue is bounded to one value per detector, failed updates are retained,
    and the latest complete snapshot is replayed periodically so integration
    reloads recover without restarting the add-on.
    """

    def __init__(
        self,
        *,
        detector_id: str = DETECTOR_ID,
        token: str | None = None,
        api_url: str = "http://supervisor/core/api",
        supervisor_url: str = "http://supervisor",
        retry_interval: float = 5.0,
        heartbeat_interval: float = 60.0,
        urlopen: UrlOpen = urllib.request.urlopen,
        clock: Clock | None = None,
    ) -> None:
        self.detector_id = detector_id
        self.api_url = api_url.rstrip("/")
        self.supervisor_url = supervisor_url.rstrip("/")
        self.token = token if token is not None else os.getenv("SUPERVISOR_TOKEN")
        self.retry_interval = retry_interval
        self.heartbeat_interval = heartbeat_interval
        self._urlopen = urlopen
        self._clock = clock or (lambda: datetime.now(UTC))

        self.connected = False
        self.discovery_uuid: str | None = None
        self._sequence = 0
        self._latest: dict[str, PendingState] = {}
        self._pending: dict[str, PendingState] = {}
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None

    def connect(self) -> bool:
        """Probe the authenticated Home Assistant Core API proxy."""

        if not self.token:
            logger.warning("SUPERVISOR_TOKEN is unavailable")
            self.connected = False
            return False

        try:
            request = self._request("GET", "/config")
            with self._urlopen(request, timeout=5) as response:
                self.connected = response.status == 200
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            OSError,
        ) as exc:
            self.connected = False
            logger.warning("Home Assistant Core API is unavailable: %s", exc)
        return self.connected

    def publish_discovery(self) -> bool:
        """Advertise the running add-on through Supervisor discovery."""

        if not self.token:
            logger.warning("Cannot publish discovery without SUPERVISOR_TOKEN")
            return False

        payload: dict[str, object] = {
            "service": DISCOVERY_SERVICE,
            "config": {
                "protocol_version": PROTOCOL_VERSION,
                "detector_id": self.detector_id,
                "source_version": __version__,
            },
        }
        try:
            request = self._request_for(
                self.supervisor_url,
                "POST",
                "/discovery",
                payload,
            )
            with self._urlopen(request, timeout=5) as response:
                if response.status not in {200, 201}:
                    return False
                body = response.read()
            response_data = json.loads(body.decode("utf-8")) if body else {}
        except (
            json.JSONDecodeError,
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            OSError,
        ) as exc:
            logger.warning("Supervisor discovery is unavailable: %s", exc)
            return False

        data = response_data.get("data", response_data)
        uuid = data.get("uuid") if isinstance(data, dict) else None
        if not isinstance(uuid, str) or not uuid:
            logger.warning("Supervisor discovery response did not contain a UUID")
            return False
        self.discovery_uuid = uuid
        logger.info("Published Acoustica discovery")
        return True

    def start(self) -> None:
        """Start the single latest-state delivery worker."""

        if not self.token or self._worker is not None:
            return
        self._stop.clear()
        self._worker = threading.Thread(
            target=self._run,
            name="ha-state-publisher",
            daemon=True,
        )
        self._worker.start()

    def update_state(
        self,
        profile_id: str,
        device_class: str,
        active: bool,
    ) -> bool:
        """Queue the newest state for one profile and return immediately."""

        if not self.token:
            logger.warning("Cannot publish state without SUPERVISOR_TOKEN")
            return False

        payload: dict[str, object] = {
            "protocol_version": PROTOCOL_VERSION,
            "detector_id": self.detector_id,
            "profile_id": profile_id,
            "device_class": device_class,
            "active": bool(active),
            "updated_at": self._clock().isoformat(),
            "source_version": __version__,
        }
        with self._lock:
            self._sequence += 1
            state = PendingState(self._sequence, payload)
            self._latest[profile_id] = state
            self._pending[profile_id] = state
        self._wake.set()
        return True

    def _run(self) -> None:
        while not self._stop.is_set():
            timeout = self.retry_interval if self.pending_count else self.heartbeat_interval
            signaled = self._wake.wait(timeout=timeout)
            self._wake.clear()
            if self._stop.is_set():
                break
            if self.pending_count:
                self._publish_pending_once()
            elif not signaled:
                self._publish_latest_once()

    def _publish_pending_once(self) -> bool:
        with self._lock:
            snapshot = list(self._pending.items())

        all_sent = True
        for profile_id, state in snapshot:
            if not self._fire_event(state.payload):
                all_sent = False
                continue
            with self._lock:
                current = self._pending.get(profile_id)
                if current is not None and current.sequence == state.sequence:
                    self._pending.pop(profile_id, None)
        return all_sent

    def _publish_latest_once(self) -> bool:
        with self._lock:
            snapshot = list(self._latest.items())

        all_sent = True
        for profile_id, state in snapshot:
            if self._fire_event(state.payload):
                continue
            all_sent = False
            with self._lock:
                current = self._latest.get(profile_id)
                if current is not None and current.sequence == state.sequence:
                    self._pending[profile_id] = state
        return all_sent

    def _fire_event(self, payload: dict[str, object]) -> bool:
        try:
            request = self._request(
                "POST",
                f"/events/{EVENT_STATE_UPDATE}",
                payload,
            )
            with self._urlopen(request, timeout=5) as response:
                success = response.status in {200, 201}
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            OSError,
        ) as exc:
            success = False
            logger.warning("State update retained for retry: %s", exc)
        self.connected = success
        return success

    def update_addon_options(self, options: dict[str, object]) -> bool:
        """Persist the complete add-on option set through Supervisor."""

        return self._post_supervisor("/addons/self/options", {"options": options})

    def _post_supervisor(self, path: str, payload: dict[str, object]) -> bool:
        if not self.token:
            logger.warning("Cannot call Supervisor without SUPERVISOR_TOKEN")
            return False
        try:
            request = self._request_for(self.supervisor_url, "POST", path, payload)
            with self._urlopen(request, timeout=10) as response:
                return response.status in {200, 201}
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            OSError,
        ) as exc:
            logger.warning("Supervisor request %s failed: %s", path, exc)
            return False

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> urllib.request.Request:
        return self._request_for(self.api_url, method, path, payload)

    def _request_for(
        self,
        base_url: str,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> urllib.request.Request:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        return urllib.request.Request(
            f"{base_url}{path}",
            data=data,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method=method,
        )

    def status(self) -> dict[str, object]:
        with self._lock:
            pending_count = len(self._pending)
            latest_count = len(self._latest)
        return {
            "connected": self.connected,
            "pending_updates": pending_count,
            "published_profiles": latest_count,
            "discovery_published": self.discovery_uuid is not None,
        }

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def disconnect(self) -> None:
        """Stop the publisher worker without blocking indefinitely."""

        self._stop.set()
        self._wake.set()
        if self._worker is not None:
            self._worker.join(timeout=2)
            self._worker = None
        self.connected = False
