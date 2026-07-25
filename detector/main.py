"""Home Assistant add-on runtime entry point."""

from __future__ import annotations

import json
import logging
import signal
import sys
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from acoustic_engine.input.listener import AudioListener

from .addon_control import AudioDeviceService
from .config import DetectorConfig
from .detector import PatternDetector
from .profile_server import ProfileServer
from .sensor import SensorManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class DetectorApp:
    """Coordinate configuration, audio capture, detection, and HA updates."""

    def __init__(
        self,
        *,
        listener_factory: Callable = AudioListener,
        detector_factory: Callable = PatternDetector,
        sensor_manager_factory: Callable = SensorManager,
        profile_server_factory: Callable = ProfileServer,
        options_path: str | Path = "/data/options.json",
    ) -> None:
        self._listener_factory = listener_factory
        self._detector_factory = detector_factory
        self._sensor_manager_factory = sensor_manager_factory
        self._profile_server_factory = profile_server_factory
        self._options_path = Path(options_path)
        self._runtime_lock = threading.RLock()

        self.config: DetectorConfig | None = None
        self.listener = None
        self.detectors: list[PatternDetector] = []
        self.sensor_manager: SensorManager | None = None
        self.profile_server: ProfileServer | None = None
        self.audio_device_service: AudioDeviceService | None = None
        self._last_detection: dict[str, str] | None = None
        self.running = False
        self._cleaned = False

    def setup(self) -> bool:
        """Initialize all runtime components without entering the capture loop."""

        try:
            self.config = DetectorConfig.from_environment()
        except (TypeError, ValueError):
            logger.exception("Invalid add-on configuration")
            return False

        if self.config.debug_mode:
            logging.getLogger().setLevel(logging.DEBUG)
        self.config.log_config()

        self.audio_device_service = AudioDeviceService(
            self.config.audio.device_index,
            persist_device=self._persist_audio_device,
            restart_addon=self._restart_addon,
        )
        self.profile_server = self._profile_server_factory(
            sample_rate=self.config.audio.sample_rate,
            chunk_size=self.config.audio.chunk_size,
            activate_profile=self.activate_profile,
            active_profile=self.active_profile,
            runtime_status=self.runtime_status,
            audio_device_service=self.audio_device_service,
        )

        self.sensor_manager = self._sensor_manager_factory(
            device_name=self.config.device_name,
            profile_names=[profile.name for profile in self.config.profiles],
            alarm_type=self.config.alarm_type,
        )
        if not self.sensor_manager.setup():
            logger.warning(
                "Home Assistant state connection is unavailable; detection will continue"
            )

        self.detectors = [
            self._detector_factory(
                profile=profile,
                audio_config=self.config.audio,
                on_detection=self._create_detection_callback(
                    self.sensor_manager,
                    profile.name,
                ),
            )
            for profile in self.config.profiles
        ]

        self.listener = self._listener_factory(
            self.config.audio,
            self._on_audio_chunk,
        )
        if not self.listener.setup():
            logger.error("No usable audio input could be opened")
            return False

        if not self.profile_server.start():
            logger.warning("The profile setup UI is unavailable")

        self._register_signal_handlers()
        logger.info("Runtime setup complete")
        return True

    def _register_signal_handlers(self) -> None:
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
        except ValueError:
            logger.debug("Signal handlers are only available on the main thread")

    def _on_audio_chunk(self, audio_chunk: np.ndarray) -> None:
        if self.profile_server is not None:
            self.profile_server.feed(audio_chunk)
        with self._runtime_lock:
            for detector in self.detectors:
                detector.process(audio_chunk)

    def _create_detection_callback(
        self,
        manager: SensorManager,
        profile_name: str,
    ) -> Callable[[bool], None]:
        publish_state = manager.create_detection_callback(profile_name)

        def callback(active: bool) -> None:
            if active:
                with self._runtime_lock:
                    self._last_detection = {
                        "profile_id": profile_name,
                        "detected_at": datetime.now(UTC).isoformat(),
                    }
            publish_state(active)

        return callback

    def runtime_status(self) -> dict[str, object]:
        """Return a non-sensitive status snapshot for the ingress dashboard."""

        with self._runtime_lock:
            manager = self.sensor_manager
            detector_states = [
                {
                    "profile_id": detector.name,
                    "active": detector.alarm_active,
                }
                for detector in self.detectors
            ]
            last_detection = (
                None if self._last_detection is None else dict(self._last_detection)
            )
            return {
                "ready": self.config is not None and self.listener is not None,
                "listening": self.running and self.listener is not None,
                "audio_device_index": (
                    None if self.config is None else self.config.audio.device_index
                ),
                "detectors": detector_states,
                "last_detection": last_detection,
                "home_assistant": (
                    manager.status()
                    if manager is not None
                    else {
                        "connected": False,
                        "pending_updates": 0,
                        "published_profiles": 0,
                        "discovery_published": False,
                    }
                ),
            }

    def active_profile(self) -> dict[str, object]:
        """Return the currently active runtime selection for the ingress UI."""

        with self._runtime_lock:
            if self.config is None:
                return {"ready": False}
            return {
                "ready": True,
                "device_name": self.config.device_name,
                "profile_id": self.config.profile_id,
                "alarm_type": self.config.alarm_type,
            }

    def activate_profile(
        self,
        profile_id: str,
        alarm_type: str,
    ) -> dict[str, object]:
        """Persist and atomically activate one saved canonical profile."""

        if self.config is None or self.profile_server is None:
            raise RuntimeError("The detector runtime is not ready")
        if alarm_type not in {"smoke", "co", "safety"}:
            raise ValueError("Unsupported alarm category")

        profile = self.profile_server.profile_store.load(profile_id)
        if (
            profile.name == self.config.profile_id
            and alarm_type == self.config.alarm_type
        ):
            return {"activated": False, **self.active_profile()}

        new_manager = self._sensor_manager_factory(
            device_name=self.config.device_name,
            profile_names=[profile.name],
            alarm_type=alarm_type,
        )
        new_detector = self._detector_factory(
            profile=profile,
            audio_config=self.config.audio,
            on_detection=self._create_detection_callback(
                new_manager,
                profile.name,
            ),
        )

        options = self._load_complete_options()
        options["profile_id"] = profile.name
        options["alarm_type"] = alarm_type
        if not new_manager.persist_addon_options(options):
            new_detector.close()
            new_manager.cleanup()
            raise RuntimeError("Could not save the active profile in Supervisor")

        connected = new_manager.setup()
        with self._runtime_lock:
            old_detectors = self.detectors
            old_manager = self.sensor_manager
            self.detectors = [new_detector]
            self.sensor_manager = new_manager
            self.config.profile_id = profile.name
            self.config.alarm_type = alarm_type
            self.config.profiles = [profile]
            self._last_detection = None

        for detector in old_detectors:
            detector.close()
        if old_manager is not None:
            old_manager.cleanup()

        logger.info(
            "Activated profile %s as %s without restarting",
            profile.name,
            alarm_type,
        )
        return {
            "activated": True,
            "home_assistant_connected": connected,
            **self.active_profile(),
        }

    def _persist_audio_device(self, device_index: int | None) -> bool:
        """Persist one microphone selection without losing unrelated options."""

        if self.sensor_manager is None:
            return False
        options = self._load_complete_options()
        options["audio_device_index"] = -1 if device_index is None else device_index
        return self.sensor_manager.persist_addon_options(options)

    def _restart_addon(self) -> bool:
        """Restart through the same authenticated Supervisor client."""

        return (
            self.sensor_manager is not None
            and self.sensor_manager.restart_addon()
        )

    def _load_complete_options(self) -> dict[str, object]:
        """Read the complete Supervisor option set for a non-destructive update."""

        try:
            options = json.loads(self._options_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("Could not read the current app options") from exc
        if not isinstance(options, dict):
            raise RuntimeError("The current app options are invalid")
        return dict(options)

    def _signal_handler(self, signum, _frame) -> None:
        logger.info("Received signal %s; shutting down", signum)
        self.running = False
        if self.listener is not None:
            self.listener.stop()

    def run(self) -> int:
        """Run the blocking capture loop and return a process exit code."""

        if self.listener is None:
            logger.error("Runtime is not set up")
            return 1

        self.running = True
        logger.info("Listening for acoustic alarm patterns")
        exit_code = 0

        try:
            self.listener.start()
            if self.running:
                logger.error("Audio capture loop exited unexpectedly")
                exit_code = 1
        except KeyboardInterrupt:
            logger.info("Shutdown requested")
            self.running = False
        except Exception:
            logger.exception("Fatal runtime error")
            exit_code = 1
        finally:
            self.cleanup()

        return exit_code

    def cleanup(self) -> None:
        """Release resources exactly once."""

        if self._cleaned:
            return
        self._cleaned = True
        self.running = False

        if self.listener is not None:
            try:
                self.listener.stop()
            finally:
                self.listener.cleanup()

        for detector in self.detectors:
            detector.close()

        if self.sensor_manager is not None:
            self.sensor_manager.cleanup()

        if self.profile_server is not None:
            self.profile_server.stop()

        logger.info("Shutdown complete")


def main() -> int:
    app = DetectorApp()
    if not app.setup():
        app.cleanup()
        return 1
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
