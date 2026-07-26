"""Bridge engine detections to Home Assistant without blocking audio capture."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Dict

from .integration_client import IntegrationClient

logger = logging.getLogger(__name__)


class HABridge:
    """Map engine detections onto integration-owned binary sensor states."""

    def __init__(
        self,
        device_classes: Dict[str, str],
        hold_seconds: float = 30.0,
        *,
        client: IntegrationClient | None = None,
        base_url: str | None = None,
        token: str | None = None,
        profiles_path=None,
        timer_factory: Callable[..., threading.Timer] = threading.Timer,
    ) -> None:
        self.device_classes = dict(device_classes)
        self.hold_seconds = hold_seconds
        self._client = client or IntegrationClient(
            token=token,
            api_url=base_url or "http://supervisor/core/api",
        )
        self._timer_factory = timer_factory
        self._lock = threading.Lock()
        self._timers: Dict[str, threading.Timer] = {}
        self._states: Dict[str, bool] = {}

    def setup(self) -> bool:
        """Start delivery, advertise discovery, and queue initial clear states."""

        connected = self._client.connect()
        self._client.start()
        if not self._client.publish_discovery():
            logger.warning("Home Assistant integration discovery was not published")
        for name, device_class in self.device_classes.items():
            self._states[name] = False
            self._client.update_state(name, device_class, False)
        return connected

    def reconfigure(self, device_classes: Dict[str, str]) -> None:
        """Replace the known detectors and publish a clear snapshot for each."""

        next_classes = dict(device_classes)
        with self._lock:
            previous_classes = dict(self.device_classes)
            removed = set(previous_classes) - set(next_classes)
            for name in removed:
                timer = self._timers.pop(name, None)
                if timer is not None:
                    timer.cancel()
            self.device_classes = next_classes
            self._states = {name: False for name in next_classes}
        for name in removed:
            self._client.update_state(
                name,
                previous_classes[name],
                False,
                removed=True,
            )
        for name, device_class in next_classes.items():
            self._client.update_state(name, device_class, False)

    def shutdown(self) -> None:
        """Cancel timers, queue clear states, and stop the publisher worker."""

        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
        for name, device_class in self.device_classes.items():
            self._client.update_state(name, device_class, False)
        self._client.disconnect()

    def on_detection(self, name: str) -> None:
        """Engine callback: a pattern named ``name`` was confirmed."""

        if name not in self.device_classes:
            logger.warning("Detection for unknown detector '%s'; using sound class", name)
            self.device_classes[name] = "sound"

        self._set(name, True)
        with self._lock:
            old = self._timers.pop(name, None)
            if old is not None:
                old.cancel()
            timer = self._timer_factory(self.hold_seconds, self._clear, args=(name,))
            timer.daemon = True
            self._timers[name] = timer
            timer.start()

    def _clear(self, name: str) -> None:
        self._set(name, False)
        with self._lock:
            self._timers.pop(name, None)

    def _set(self, name: str, state: bool) -> None:
        with self._lock:
            if self._states.get(name) == state:
                return
            self._states[name] = state
        device_class = self.device_classes.get(name, "sound")
        logger.info("%s -> %s", name, "DETECTED" if state else "clear")
        self._client.update_state(name, device_class, state)

    def status(self) -> dict[str, object]:
        """Return non-sensitive state for the ingress runtime panel."""

        with self._lock:
            active = sorted(name for name, state in self._states.items() if state)
        return {
            "home_assistant": self._client.status(),
            "active_matches": active,
            "detectors": [
                {"name": name, "device_class": device_class}
                for name, device_class in self.device_classes.items()
            ],
        }

    def persist_options(self, options: dict[str, object]) -> bool:
        """Persist the complete Supervisor option set."""

        return self._client.update_addon_options(options)
