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

from acoustic_engine.input.listener import AudioListener, list_input_devices
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
_ALLOWED_SOURCE_KINDS = {"preset", "profile", "learn"}
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


def _probe_audio_settings(audio_config) -> tuple[bool, str | None]:
    """Open and close a candidate microphone before committing its options."""

    listener = AudioListener(audio_config, lambda _chunk: None)
    try:
        if not listener.setup():
            return False, "The selected microphone could not be opened"
        return True, None
    except Exception as exc:
        logger.warning("Microphone preflight failed: %s", exc)
        return False, str(exc)
    finally:
        try:
            listener.cleanup()
        except Exception:
            logger.debug("Microphone preflight cleanup failed", exc_info=True)


class DetectorApp:
    """Own the engine, Home Assistant bridge, and local control plane."""

    def __init__(
        self,
        *,
        engine_factory: Callable = ParallelEngine,
        bridge_factory: Callable = HABridge,
        control_server_factory: Callable = ControlServer,
        device_lister: Callable = list_input_devices,
        audio_probe: Callable = _probe_audio_settings,
    ) -> None:
        self._engine_factory = engine_factory
        self._bridge_factory = bridge_factory
        self._control_server_factory = control_server_factory
        self._device_lister = device_lister
        self._audio_probe = audio_probe
        self._condition = threading.Condition()
        self._reload_lock = threading.Lock()

        self.config: AppConfig | None = None
        self.bridge: HABridge | None = None
        self.engine = None
        self.control_server: ControlServer | None = None

        self._pending_config: AppConfig | None = None
        self._pending_engine = None
        self._reload_requested = False
        self._reload_preparing = False
        self._resume_current = False
        self._rollback_config: AppConfig | None = None
        self._rollback_engine = None
        self._rollback_options: dict[str, object] | None = None
        self._rollback_timer: threading.Timer | None = None
        self._shutdown = False
        self._generation = 0
        self._runtime_state = "starting"
        self._last_detection: dict[str, str] | None = None
        self._last_error: str | None = None

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
            disable_detector=self.disable_detector,
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
        """Run engine generations until shutdown or an unrecoverable audio exit."""

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
                self._condition.notify_all()

            logger.info("Listening on the microphone")
            run_error: str | None = None
            try:
                engine.start()
            except KeyboardInterrupt:
                self._handle_signal(signal.SIGINT, None)
            except Exception as exc:
                run_error = str(exc) or exc.__class__.__name__
                logger.exception("Fatal error in detection loop")
                exit_code = 1

            next_config: AppConfig | None = None
            with self._condition:
                if self._shutdown:
                    break

                while self._reload_preparing and not self._shutdown:
                    self._condition.wait(timeout=0.5)
                if self._shutdown:
                    break

                if self._reload_requested and self._pending_config is not None:
                    previous_config = self.config
                    previous_engine = self.engine
                    self.config = self._pending_config
                    self.engine = self._pending_engine
                    self._pending_config = None
                    self._pending_engine = None
                    self._reload_requested = False
                    self._generation += 1
                    exit_code = 0
                    self._runtime_state = "starting"
                    self._last_error = None
                    self._rollback_config = previous_config
                    self._rollback_engine = previous_engine
                    self._rollback_options = (
                        dict(previous_config.options) if previous_config is not None else None
                    )
                    next_config = self.config
                    if self.bridge is not None:
                        self.bridge.hold_seconds = self.config.hold_seconds
                        self.bridge.reconfigure(self.config.device_classes)
                    self._condition.notify_all()

                elif self._resume_current:
                    self._resume_current = False
                    exit_code = 0
                    self._runtime_state = "starting"
                    self._condition.notify_all()
                    continue

            if next_config is not None:
                self._log_generation(next_config)
                self._arm_rollback_window(self._generation)
                continue

            reason = run_error or "Audio capture loop exited unexpectedly"
            if self._restore_previous_generation(reason):
                exit_code = 0
                continue

            logger.error(reason)
            with self._condition:
                self._last_error = reason
                self._runtime_state = "error"
            exit_code = 1
            break

        self.cleanup()
        return exit_code

    def _arm_rollback_window(self, generation: int) -> None:
        """Keep the previous generation briefly, then discard it once stable."""

        with self._condition:
            if self._rollback_timer is not None:
                self._rollback_timer.cancel()
            timer = threading.Timer(10.0, self._expire_rollback, args=(generation,))
            timer.daemon = True
            self._rollback_timer = timer
            timer.start()

    def _expire_rollback(self, generation: int) -> None:
        with self._condition:
            if self._generation != generation or self._shutdown:
                return
            self._rollback_config = None
            self._rollback_engine = None
            self._rollback_options = None
            self._rollback_timer = None

    def _restore_previous_generation(self, reason: str) -> bool:
        """Restore the prior options and engine when a new generation dies early."""

        with self._condition:
            config = self._rollback_config
            engine = self._rollback_engine
            options = self._rollback_options
        if config is None or engine is None or options is None or self.bridge is None:
            return False

        if not self.bridge.persist_options(options):
            logger.error("Could not restore previous add-on options after: %s", reason)
            return False

        with self._condition:
            if self._rollback_timer is not None:
                self._rollback_timer.cancel()
                self._rollback_timer = None
            self.config = config
            self.engine = engine
            self._rollback_config = None
            self._rollback_engine = None
            self._rollback_options = None
            self._generation += 1
            self._runtime_state = "recovering"
            self._last_error = f"{reason}; restored the previous audio generation"
            self.bridge.hold_seconds = config.hold_seconds
            self.bridge.reconfigure(config.device_classes)
            self._condition.notify_all()

        logger.warning("%s; restored generation %d", reason, self._generation)
        self._log_generation(config)
        return True

    def request_reconfigure(self, options: dict[str, object]) -> dict[str, object]:
        """Preflight, persist, and atomically request a new engine generation."""

        with self._reload_lock:
            with self._condition:
                if self._shutdown:
                    raise RuntimeError("The detector is shutting down")

            candidate_config = load_app_config(options)
            if not candidate_config.detectors:
                raise ValueError("At least one valid detector must remain configured")
            candidate_engine = self._build_engine(candidate_config)

            with self._condition:
                if self._rollback_timer is not None:
                    self._rollback_timer.cancel()
                    self._rollback_timer = None
                self._rollback_config = None
                self._rollback_engine = None
                self._rollback_options = None
                self._reload_preparing = True
                self._runtime_state = "validating"
                current_engine = self.engine

            if current_engine is not None:
                current_engine.stop()

            probe_ok, probe_error = self._audio_probe(candidate_config.audio)
            if not probe_ok:
                message = probe_error or "The selected microphone could not be opened"
                with self._condition:
                    self._reload_preparing = False
                    self._resume_current = True
                    self._runtime_state = "recovering"
                    self._last_error = message
                    self._condition.notify_all()
                raise RuntimeError(message)

            if self.bridge is None or not self.bridge.persist_options(options):
                with self._condition:
                    self._reload_preparing = False
                    self._resume_current = True
                    self._runtime_state = "recovering"
                    self._last_error = "Home Assistant could not save the add-on options"
                    self._condition.notify_all()
                raise RuntimeError("Home Assistant could not save the add-on options")

            with self._condition:
                if self._shutdown:
                    self._reload_preparing = False
                    self._resume_current = True
                    self._condition.notify_all()
                    raise RuntimeError("The detector is shutting down")
                target_generation = self._generation + 1
                self._pending_config = candidate_config
                self._pending_engine = candidate_engine
                self._reload_requested = True
                self._reload_preparing = False
                self._runtime_state = "reloading"
                self._condition.notify_all()

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

    def disable_detector(
        self,
        source_kind: str,
        source_value: str,
    ) -> dict[str, object]:
        """Disable one configured source and hot-reload the remaining detectors."""

        if source_kind not in _ALLOWED_SOURCE_KINDS:
            raise ValueError("Unsupported detector source")
        source_value = source_value.strip()
        if not source_value:
            raise ValueError("Detector source is required")

        options = self._complete_options()
        raw_detectors = options.get("detectors")
        detectors = [
            dict(item)
            for item in raw_detectors
            if isinstance(item, dict)
        ] if isinstance(raw_detectors, list) else []
        remaining = [
            item
            for item in detectors
            if str(item.get(source_kind, "")) != source_value
        ]
        if len(remaining) == len(detectors):
            raise ValueError("The detector source is no longer configured")
        options["detectors"] = remaining
        return {
            "disabled": True,
            "source_kind": source_kind,
            "source_value": source_value,
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
        raw_detectors = current.get("detectors")
        if not isinstance(raw_detectors, list) or not raw_detectors:
            current["detectors"] = [
                {
                    "name": detector.profile.name,
                    detector.source_kind: detector.source_value,
                    "device_class": detector.device_class,
                }
                for detector in (self.config.detectors if self.config is not None else [])
            ]
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
            last_error = self._last_error
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
            "last_error": last_error,
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
        with self._condition:
            if self._rollback_timer is not None:
                self._rollback_timer.cancel()
                self._rollback_timer = None
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
