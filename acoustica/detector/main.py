"""Acoustica add-on runtime with hot-reloadable engine generations."""

from __future__ import annotations

import logging
import re
import signal
import sys
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from acoustic_engine.input.listener import list_input_devices
from acoustic_engine.parallel_engine import ParallelEngine
from acoustic_engine.profiles import load_profiles_from_yaml

from detector.config import AppConfig, load_app_config, profiles_dir, read_options
from detector.control_server import ControlServer
from detector.ha_bridge import HABridge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("acoustica")

_SAFE_PROFILE = re.compile(r"^[A-Za-z0-9_.-]+$")
_ALLOWED_DEVICE_CLASSES = {
    "smoke",
    "carbon_monoxide",
    "gas",
    "sound",
    "moisture",
    "safety",
    "problem",
    "running",
    "vibration",
}


class _DropMatcherHeartbeat(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "evaluating" not in record.getMessage().lower()


class DetectorApp:
    """Own the engine, Home Assistant bridge, and local control plane."""

    def __init__(
        self,
        *,
        engine_factory: Callable = ParallelEngine,
        bridge_factory: Callable = HABridge,
        control_server_factory: Callable = ControlServer,
        device_lister: Callable = list_input_devices,
    ) -> None:
        self._engine_factory = engine_factory
        self._bridge_factory = bridge_factory
        self._control_server_factory = control_server_factory
        self._device_lister = device_lister
        self._condition = threading.Condition()
        self._reload_lock = threading.Lock()

        self.config: AppConfig | None = None
        self.bridge: HABridge | None = None
        self.engine = None
        self.control_server: ControlServer | None = None

        self._pending_config: AppConfig | None = None
        self._pending_engine = None
        self._reload_requested = False
        self._shutdown = False
        self._generation = 0
        self._runtime_state = "starting"
        self._last_detection: dict[str, str] | None = None

    def setup(self) -> bool:
        """Build the first runtime generation and start the local control API."""

        try:
            config = load_app_config()
        except Exception:
            logger.exception("Could not load add-on configuration")
            return False
        if not config.detectors:
            logger.error("No usable detectors are configured")
            return False

        self._configure_logging(config)
        self.config = config
        self.bridge = self._bridge_factory(
            device_classes=config.device_classes,
            hold_seconds=config.hold_seconds,
        )
        if not self.bridge.setup():
            logger.warning("Home Assistant is unavailable; state delivery will retry")
        self.engine = self._build_engine(config)
        self.control_server = self._control_server_factory(
            status=self.status,
            activate_profile=self.activate_profile,
            select_audio_device=self.select_audio_device,
        )
        if not self.control_server.start():
            logger.error("The local tuner control API could not start")
            return False

        self._register_signal_handlers()
        self._log_generation(config)
        return True

    def _configure_logging(self, config: AppConfig) -> None:
        if not config.debug:
            return
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("acoustic_engine").setLevel(logging.DEBUG)
        logging.getLogger("acoustic_engine.analysis.windowed_matcher").addFilter(
            _DropMatcherHeartbeat()
        )

    def _build_engine(self, config: AppConfig):
        return self._engine_factory(
            pipelines=config.profiles,
            audio_config=config.audio,
            on_detection=self._on_detection,
        )

    def _on_detection(self, name: str) -> None:
        with self._condition:
            self._last_detection = {
                "profile_id": name,
                "at": datetime.now(UTC).isoformat(),
            }
        if self.bridge is not None:
            self.bridge.on_detection(name)

    def _register_signal_handlers(self) -> None:
        try:
            signal.signal(signal.SIGTERM, self._handle_signal)
            signal.signal(signal.SIGINT, self._handle_signal)
        except ValueError:
            logger.debug("Signal handlers are only available on the main thread")

    def _handle_signal(self, signum, _frame) -> None:
        logger.info("Received signal %s; shutting down", signum)
        with self._condition:
            self._shutdown = True
            self._runtime_state = "stopping"
            engine = self.engine
            self._condition.notify_all()
        if engine is not None:
            engine.stop()

    def run(self) -> int:
        """Run engine generations until shutdown or an unexpected audio exit."""

        if self.engine is None or self.config is None:
            logger.error("Runtime is not set up")
            return 1

        exit_code = 0
        while True:
            with self._condition:
                if self._shutdown:
                    break
                engine = self.engine
                self._runtime_state = "listening"

            logger.info("Listening on the microphone")
            try:
                engine.start()
            except KeyboardInterrupt:
                self._handle_signal(signal.SIGINT, None)
            except Exception:
                logger.exception("Fatal error in detection loop")
                exit_code = 1

            with self._condition:
                if self._shutdown:
                    break
                if self._reload_requested and self._pending_config is not None:
                    self.config = self._pending_config
                    self.engine = self._pending_engine
                    self._pending_config = None
                    self._pending_engine = None
                    self._reload_requested = False
                    self._generation += 1
                    exit_code = 0
                    self._runtime_state = "starting"
                    if self.bridge is not None:
                        self.bridge.hold_seconds = self.config.hold_seconds
                        self.bridge.reconfigure(self.config.device_classes)
                    self._condition.notify_all()
                    self._log_generation(self.config)
                    continue

                if exit_code == 0:
                    logger.error("Audio capture loop exited unexpectedly")
                    exit_code = 1
                self._runtime_state = "error"
                break

        self.cleanup()
        return exit_code

    def request_reconfigure(self, options: dict[str, object]) -> dict[str, object]:
        """Validate, persist, and atomically request a new engine generation."""

        with self._reload_lock:
            with self._condition:
                if self._shutdown:
                    raise RuntimeError("The detector is shutting down")

            candidate_config = load_app_config(options)
            if not candidate_config.detectors:
                raise ValueError("At least one valid detector must remain configured")
            candidate_engine = self._build_engine(candidate_config)

            if self.bridge is None or not self.bridge.persist_options(options):
                raise RuntimeError("Home Assistant could not save the add-on options")

            with self._condition:
                if self._shutdown:
                    raise RuntimeError("The detector is shutting down")
                target_generation = self._generation + 1
                self._pending_config = candidate_config
                self._pending_engine = candidate_engine
                self._reload_requested = True
                self._runtime_state = "reloading"
                current_engine = self.engine

            if current_engine is not None:
                current_engine.stop()

            with self._condition:
                completed = self._condition.wait_for(
                    lambda: self._generation >= target_generation or self._shutdown,
                    timeout=15,
                )
                if not completed or self._generation < target_generation:
                    raise RuntimeError("The audio engine did not reload in time")
            return {"reloaded": True, **self.status()}

    def activate_profile(
        self,
        profile_id: str,
        device_class: str,
    ) -> dict[str, object]:
        """Enable one saved tuner profile without restarting the add-on."""

        profile_id = profile_id.strip()
        if not _SAFE_PROFILE.fullmatch(profile_id):
            raise ValueError("Invalid profile ID")
        if device_class not in _ALLOWED_DEVICE_CLASSES:
            raise ValueError("Unsupported Home Assistant device class")

        profile_path = profiles_dir() / f"{profile_id}.yaml"
        if not profile_path.is_file():
            raise ValueError(f"No saved profile named '{profile_id}'")
        profiles = load_profiles_from_yaml(profile_path)
        if len(profiles) != 1:
            raise ValueError("Only single-profile YAML files can be enabled from the tuner")
        detector_name = profiles[0].name

        options = self._complete_options()
        raw_detectors = options.get("detectors")
        detectors = [
            dict(item)
            for item in raw_detectors
            if isinstance(item, dict)
        ] if isinstance(raw_detectors, list) else []
        entry = {
            "name": detector_name,
            "profile": profile_path.name,
            "device_class": device_class,
        }
        detectors = [
            item
            for item in detectors
            if item.get("profile") != profile_path.name
            and item.get("name") != detector_name
        ]
        detectors.append(entry)
        options["detectors"] = detectors
        return {
            "profile_id": profile_id,
            "detector_name": detector_name,
            **self.request_reconfigure(options),
        }

    def select_audio_device(self, device_index: int | None) -> dict[str, object]:
        """Validate and hot-reload the selected engine input device."""

        devices = self._device_lister()
        if device_index is not None:
            available = {
                int(device["index"])
                for device in devices
                if isinstance(device, dict) and "index" in device
            }
            if device_index not in available:
                raise ValueError(f"Audio device {device_index} is not available")

        options = self._complete_options()
        options["device_index"] = -1 if device_index is None else device_index
        return self.request_reconfigure(options)

    def _complete_options(self) -> dict[str, object]:
        current = dict(self.config.options if self.config is not None else read_options())
        current.setdefault("detectors", [])
        current.setdefault("sample_rate", 44100)
        current.setdefault("device_index", -1)
        current.setdefault("hold_seconds", 30)
        current.setdefault("debug", False)
        return current

    def status(self) -> dict[str, object]:
        """Return the current runtime generation for the ingress panel."""

        with self._condition:
            config = self.config
            state = self._runtime_state
            generation = self._generation
            last_detection = self._last_detection
        detector_rows = []
        if config is not None:
            detector_rows = [
                {
                    "name": detector.profile.name,
                    "device_class": detector.device_class,
                    "source_kind": detector.source_kind,
                    "source_value": detector.source_value,
                }
                for detector in config.detectors
            ]
        bridge_status = self.bridge.status() if self.bridge is not None else {}
        return {
            **bridge_status,
            "ready": config is not None and self.engine is not None,
            "state": state,
            "generation": generation,
            "audio": {
                "sample_rate": config.audio.sample_rate if config else None,
                "device_index": config.audio.device_index if config else None,
            },
            "detectors": detector_rows,
            "last_detection": last_detection,
        }

    def _log_generation(self, config: AppConfig) -> None:
        logger.info(
            "Runtime generation %d: %d detector(s), %d Hz, device=%s",
            self._generation,
            len(config.detectors),
            config.audio.sample_rate,
            config.audio.device_index if config.audio.device_index is not None else "default",
        )
        for detector in config.detectors:
            logger.info(
                "Detector: %r [%s, %s=%s]",
                detector.profile.name,
                detector.device_class,
                detector.source_kind,
                detector.source_value,
            )

    def cleanup(self) -> None:
        if self.control_server is not None:
            self.control_server.stop()
        if self.bridge is not None:
            self.bridge.shutdown()
        logger.info("Shutdown complete")


def main() -> int:
    app = DetectorApp()
    if not app.setup():
        app.cleanup()
        return 1
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
