"""Audio-device selection using the existing runtime Supervisor control path."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from acoustic_engine.input.listener import list_input_devices

DeviceLister = Callable[[], list[dict]]
PersistDevice = Callable[[int | None], bool]
RestartAddon = Callable[[], bool]
TimerFactory = Callable[[float, Callable[[], None]], threading.Timer]

logger = logging.getLogger(__name__)


class AudioDeviceService:
    """List input devices and persist one validated selection.

    Supervisor communication is injected by ``DetectorApp`` so profile activation
    and microphone selection share one authenticated client and one option-update
    implementation.
    """

    def __init__(
        self,
        current_index: int | None,
        *,
        persist_device: PersistDevice,
        restart_addon: RestartAddon,
        device_lister: DeviceLister = list_input_devices,
        timer_factory: TimerFactory = threading.Timer,
    ) -> None:
        self.current_index = current_index
        self._persist_device = persist_device
        self._restart_addon = restart_addon
        self._device_lister = device_lister
        self._timer_factory = timer_factory

    def status(self) -> dict[str, object]:
        """Return safe device metadata for the ingress UI."""

        devices = [self._normalize_device(item) for item in self._device_lister()]
        return {
            "current_index": self.current_index,
            "devices": devices,
        }

    def select(self, device_index: int | None) -> dict[str, object]:
        """Validate and persist a device selection."""

        status = self.status()
        if device_index is not None:
            available = {item["index"] for item in status["devices"]}
            if device_index not in available:
                raise ValueError(f"Audio device index {device_index} is not available")

        if not self._persist_device(device_index):
            raise RuntimeError("Home Assistant could not save the microphone selection")

        self.current_index = device_index
        status["current_index"] = device_index
        return status

    def schedule_restart(self, delay: float = 1.0) -> None:
        """Restart after the HTTP response has been sent to the browser."""

        timer = self._timer_factory(delay, self._restart)
        timer.daemon = True
        timer.start()

    def _restart(self) -> None:
        if not self._restart_addon():
            logger.error("Home Assistant could not restart the add-on")

    @staticmethod
    def _normalize_device(item: dict) -> dict[str, object]:
        return {
            "index": int(item["index"]),
            "name": str(item.get("name", "Unknown microphone")),
            "channels": int(item.get("channels", 0)),
            "default": bool(item.get("default", False)),
            "backend": str(item.get("backend", "unknown")),
        }
