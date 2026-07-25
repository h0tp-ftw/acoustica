"""Home Assistant state publication for detected profiles."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

from .integration_client import IntegrationClient

logger = logging.getLogger(__name__)


class SensorManager:
    """Route detector state changes through one Home Assistant publisher."""

    def __init__(
        self,
        device_name: str,
        profile_names: Iterable[str],
        alarm_type: str,
        *,
        client: IntegrationClient | None = None,
    ) -> None:
        self.device_name = device_name
        self.profile_names = tuple(profile_names)
        self.alarm_type = alarm_type
        self._profile_set = frozenset(self.profile_names)
        self._client = client or IntegrationClient(
            detector_id=device_name,
            alarm_type=alarm_type,
        )

    def setup(self) -> bool:
        """Probe Home Assistant, start retry delivery, and publish initial clear states."""

        connected = self._client.connect()
        self._client.start()

        if self.profile_names and not self._client.publish_discovery(
            self.profile_names[0]
        ):
            logger.warning("Home Assistant integration discovery was not published")

        for profile_name in self.profile_names:
            self._client.update_state(profile_name, False)

        if connected:
            logger.info("Home Assistant state publisher is connected")
        else:
            logger.warning("Home Assistant updates will retry in the background")
        return connected

    def persist_addon_options(self, options: dict[str, object]) -> bool:
        """Persist the complete option set before a hot profile activation."""

        return self._client.update_addon_options(options)

    def status(self) -> dict[str, object]:
        """Return the Home Assistant publisher health for ingress diagnostics."""

        return self._client.status()

    def restart_addon(self) -> bool:
        """Request an app restart after a microphone selection changes."""

        return self._client.restart_addon()

    def update_state(self, profile_name: str, detected: bool) -> bool:
        """Queue the latest state for one known profile."""

        if profile_name not in self._profile_set:
            logger.error("Unknown detector profile: %s", profile_name)
            return False

        queued = self._client.update_state(profile_name, detected)
        if queued:
            logger.info(
                "Queued %s state for %s",
                "active" if detected else "clear",
                profile_name,
            )
        return queued

    def create_detection_callback(self, profile_name: str) -> Callable[[bool], None]:
        """Create the callback used by one pattern detector."""

        def callback(detected: bool) -> None:
            self.update_state(profile_name, detected)

        return callback

    def cleanup(self) -> None:
        self._client.disconnect()
