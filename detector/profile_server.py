"""Small ingress HTTP server for guided profile learning."""

from __future__ import annotations

import io
import json
import logging
import os
import tempfile
import threading
import wave
from collections.abc import Callable
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import numpy as np
from acoustic_engine.config import AudioSettings

from . import __version__
from .addon_control import AudioDeviceService
from .detector import PatternDetector
from .profile_service import ProfileStore, profile_to_yaml

logger = logging.getLogger(__name__)

MAX_IMPORT_BYTES = 2 * 1024 * 1024
DEFAULT_PORT = 8099
DEFAULT_RECORDING_SECONDS = 30.0
DEFAULT_TEST_SECONDS = 60.0

ActivationCallback = Callable[[str, str], dict[str, object]]
ActiveProfileCallback = Callable[[], dict[str, object]]
RuntimeStatusCallback = Callable[[], dict[str, object]]


class ProfileTestSession:
    """Bounded live profile test that never publishes Home Assistant state."""

    def __init__(
        self,
        profile_store: ProfileStore,
        sample_rate: int,
        chunk_size: int,
        *,
        max_seconds: float = DEFAULT_TEST_SECONDS,
    ) -> None:
        self.profile_store = profile_store
        self.audio_settings = AudioSettings(
            sample_rate=sample_rate,
            chunk_size=chunk_size,
            channels=1,
        )
        self.max_samples = round(sample_rate * max_seconds)
        self._detector: PatternDetector | None = None
        self._profile_id: str | None = None
        self._sample_count = 0
        self._match_count = 0
        self._error: str | None = None
        self._testing = False
        self._lock = threading.Lock()

    def start(self, profile_id: str) -> dict[str, object]:
        """Start testing one saved profile on future production audio chunks."""

        profile = self.profile_store.load(profile_id)
        detector = PatternDetector(
            profile=profile,
            audio_config=self.audio_settings,
            on_detection=self._handle_detection,
        )

        old_detector: PatternDetector | None
        with self._lock:
            old_detector = self._detector
            self._detector = detector
            self._profile_id = profile.name
            self._sample_count = 0
            self._match_count = 0
            self._error = None
            self._testing = True
            status = self._status_locked()

        if old_detector is not None:
            old_detector.close()
        return status

    def stop(self) -> dict[str, object]:
        detector: PatternDetector | None
        with self._lock:
            detector = self._detector
            self._detector = None
            self._testing = False
            status = self._status_locked()
        if detector is not None:
            detector.close()
        return status

    def feed(self, audio_chunk: np.ndarray) -> None:
        with self._lock:
            if not self._testing or self._detector is None:
                return
            detector = self._detector

        try:
            detector.process(audio_chunk)
        except Exception as exc:
            logger.exception("Live profile test failed")
            with self._lock:
                if detector is self._detector:
                    self._error = str(exc)
            self.stop()
            return

        should_stop = False
        with self._lock:
            if detector is not self._detector:
                return
            self._sample_count += len(audio_chunk)
            should_stop = self._sample_count >= self.max_samples
        if should_stop:
            self.stop()

    def status(self) -> dict[str, object]:
        with self._lock:
            return self._status_locked()

    def _handle_detection(self, active: bool) -> None:
        if not active:
            return
        with self._lock:
            if self._testing:
                self._match_count += 1

    def _status_locked(self) -> dict[str, object]:
        return {
            "testing": self._testing,
            "profile_id": self._profile_id,
            "matched": self._match_count > 0,
            "match_count": self._match_count,
            "error": self._error,
            "duration_seconds": round(
                self._sample_count / self.audio_settings.sample_rate,
                2,
            ),
            "max_seconds": round(
                self.max_samples / self.audio_settings.sample_rate,
                1,
            ),
        }


class RecordingSession:
    """Thread-safe tap on the add-on's production microphone stream."""

    def __init__(
        self,
        sample_rate: int,
        *,
        max_seconds: float = DEFAULT_RECORDING_SECONDS,
    ) -> None:
        self.sample_rate = sample_rate
        self.max_samples = round(sample_rate * max_seconds)
        self._chunks: list[np.ndarray] = []
        self._sample_count = 0
        self._level = 0.0
        self._recording = False
        self._lock = threading.Lock()

    def start(self) -> dict[str, object]:
        """Discard the old sample and begin capturing live detector audio."""

        with self._lock:
            self._chunks.clear()
            self._sample_count = 0
            self._level = 0.0
            self._recording = True
            return self._status_locked()

    def stop(self) -> dict[str, object]:
        with self._lock:
            self._recording = False
            self._level = 0.0
            return self._status_locked()

    def feed(self, audio_chunk: np.ndarray) -> None:
        """Copy one production audio chunk while a recording is active."""

        with self._lock:
            if not self._recording:
                return

            chunk = np.asarray(audio_chunk, dtype=np.int16).reshape(-1)
            remaining = self.max_samples - self._sample_count
            if remaining <= 0:
                self._recording = False
                self._level = 0.0
                return

            captured = np.ascontiguousarray(chunk[:remaining], dtype=np.int16)
            if captured.size:
                self._chunks.append(captured.copy())
                self._sample_count += captured.size
                normalized = captured.astype(np.float64) / 32768.0
                self._level = min(
                    1.0,
                    float(np.sqrt(np.mean(normalized**2))) * 5.0,
                )

            if self._sample_count >= self.max_samples:
                self._recording = False
                self._level = 0.0

    def snapshot(self) -> np.ndarray:
        """Return a stable copy of the current recording."""

        with self._lock:
            if self._recording:
                raise ValueError("Stop the recording before analyzing it")
            if not self._chunks:
                raise ValueError("Record an alarm sample first")
            return np.concatenate(self._chunks).copy()

    def status(self) -> dict[str, object]:
        with self._lock:
            return self._status_locked()

    def wav_bytes(self) -> bytes:
        """Encode the captured production stream as mono 16-bit PCM WAV."""

        audio = self.snapshot()
        output = io.BytesIO()
        with wave.open(output, "wb") as recording:
            recording.setnchannels(1)
            recording.setsampwidth(2)
            recording.setframerate(self.sample_rate)
            recording.writeframes(audio.tobytes())
        return output.getvalue()

    def _status_locked(self) -> dict[str, object]:
        return {
            "recording": self._recording,
            "has_recording": self._sample_count > 0,
            "duration_seconds": round(self._sample_count / self.sample_rate, 2),
            "level": round(self._level, 4),
            "max_seconds": round(self.max_samples / self.sample_rate, 1),
        }


class ProfileServer:
    """Serve the ingress UI and profile-management API in one daemon thread."""

    def __init__(
        self,
        *,
        sample_rate: int = 44100,
        chunk_size: int = 1024,
        host: str = "0.0.0.0",
        port: int | None = None,
        profile_store: ProfileStore | None = None,
        recording_session: RecordingSession | None = None,
        test_session: ProfileTestSession | None = None,
        activate_profile: ActivationCallback | None = None,
        active_profile: ActiveProfileCallback | None = None,
        runtime_status: RuntimeStatusCallback | None = None,
        audio_device_service: AudioDeviceService | None = None,
        static_root: str | Path | None = None,
        allowed_clients: set[str] | None = None,
    ) -> None:
        self.host = host
        self.port = port if port is not None else int(
            os.getenv("INGRESS_PORT", str(DEFAULT_PORT))
        )
        self.profile_store = profile_store or ProfileStore()
        self.recording_session = recording_session or RecordingSession(sample_rate)
        self.test_session = test_session or ProfileTestSession(
            self.profile_store,
            sample_rate,
            chunk_size,
        )
        self.activate_profile = activate_profile
        self.active_profile = active_profile
        self.runtime_status = runtime_status
        self.audio_device_service = audio_device_service
        self.static_root = Path(static_root or Path(__file__).parents[1] / "tuner")
        configured_clients = os.getenv("INGRESS_ALLOWED_CLIENTS", "172.30.32.2")
        self.allowed_clients = allowed_clients or {
            value.strip() for value in configured_clients.split(",") if value.strip()
        }
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        """Bind and start the HTTP server."""

        if self._server is not None:
            return True

        handler = _handler_factory(
            self.profile_store,
            self.recording_session,
            self.test_session,
            self.activate_profile,
            self.active_profile,
            self.runtime_status,
            self.audio_device_service,
            self.static_root,
            self.allowed_clients,
        )
        try:
            self._server = ThreadingHTTPServer((self.host, self.port), handler)
        except OSError as exc:
            logger.error("Could not start profile UI on port %s: %s", self.port, exc)
            return False

        self.port = self._server.server_port
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="profile-ui",
            daemon=True,
        )
        self._thread.start()
        logger.info("Profile UI listening on port %s", self.port)
        return True

    def feed(self, audio_chunk: np.ndarray) -> None:
        self.recording_session.feed(audio_chunk)
        self.test_session.feed(audio_chunk)

    def stop(self) -> None:
        """Stop recording and release the HTTP server."""

        self.recording_session.stop()
        self.test_session.stop()
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._thread = None
        self._server = None


def _handler_factory(
    profile_store: ProfileStore,
    recording_session: RecordingSession,
    test_session: ProfileTestSession,
    activate_profile: ActivationCallback | None,
    active_profile: ActiveProfileCallback | None,
    runtime_status: RuntimeStatusCallback | None,
    audio_device_service: AudioDeviceService | None,
    static_root: Path,
    allowed_clients: set[str],
):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"AcousticAlarmDetector/{__version__}"

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            if not self._client_allowed():
                return
            parsed = urlsplit(self.path)
            if parsed.path == "/api/health":
                self._json(
                    {
                        "status": "ok",
                        "version": __version__,
                        "profiles": len(profile_store.list()),
                        "recording": recording_session.status(),
                        "profile_test": test_session.status(),
                        "active_profile": (
                            active_profile() if active_profile is not None else None
                        ),
                        "runtime": (
                            runtime_status() if runtime_status is not None else None
                        ),
                    }
                )
                return
            if parsed.path == "/api/audio/devices":
                if audio_device_service is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "Microphone selection is unavailable",
                    )
                    return
                try:
                    self._json(audio_device_service.status())
                except Exception as exc:
                    self._error(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
                return
            if parsed.path == "/api/record/status":
                self._json(recording_session.status())
                return
            if parsed.path == "/api/record/audio":
                try:
                    self._send(recording_session.wav_bytes(), "audio/wav")
                except ValueError as exc:
                    self._error(HTTPStatus.NOT_FOUND, str(exc))
                return
            if parsed.path == "/api/test/status":
                self._json(test_session.status())
                return
            if parsed.path == "/api/profiles":
                self._json([asdict(item) for item in profile_store.list()])
                return
            if parsed.path.startswith("/api/profiles/"):
                profile_id = unquote(parsed.path.removeprefix("/api/profiles/"))
                try:
                    yaml_text = profile_store.path_for(profile_id).read_text(
                        encoding="utf-8"
                    )
                except (FileNotFoundError, ValueError) as exc:
                    self._error(HTTPStatus.NOT_FOUND, str(exc))
                    return
                self._text(yaml_text, "application/yaml; charset=utf-8")
                return

            self._serve_static(parsed.path)

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            if not self._client_allowed():
                return
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)

            if parsed.path == "/api/audio/select":
                if audio_device_service is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "Microphone selection is unavailable",
                    )
                    return
                raw_index = _required_query(query, "device_index")
                if raw_index is None:
                    self._error(HTTPStatus.BAD_REQUEST, "device_index is required")
                    return
                try:
                    device_index = (
                        None if raw_index in {"default", "-1"} else int(raw_index)
                    )
                    status = audio_device_service.select(device_index)
                    self._json({"saved": True, **status})
                    audio_device_service.schedule_restart()
                except (TypeError, ValueError, RuntimeError) as exc:
                    self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            if parsed.path == "/api/record/start":
                self._json(recording_session.start())
                return
            if parsed.path == "/api/record/stop":
                self._json(recording_session.stop())
                return
            if parsed.path == "/api/test/start":
                profile_id = _required_query(query, "profile_id")
                if profile_id is None:
                    self._error(HTTPStatus.BAD_REQUEST, "profile_id is required")
                    return
                try:
                    self._json(test_session.start(profile_id))
                except Exception as exc:
                    self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            if parsed.path == "/api/test/stop":
                self._json(test_session.stop())
                return

            if parsed.path.startswith("/api/profiles/") and parsed.path.endswith(
                "/activate"
            ):
                if activate_profile is None:
                    self._error(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "Profile activation is unavailable",
                    )
                    return
                profile_id = unquote(
                    parsed.path.removeprefix("/api/profiles/").removesuffix(
                        "/activate"
                    )
                ).strip("/")
                alarm_type = _required_query(query, "alarm_type")
                if alarm_type not in {"smoke", "co", "safety"}:
                    self._error(
                        HTTPStatus.BAD_REQUEST,
                        "alarm_type must be smoke, co, or safety",
                    )
                    return
                try:
                    self._json(activate_profile(profile_id, alarm_type))
                except Exception as exc:
                    self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return

            if parsed.path == "/api/analyze":
                profile_id = _required_query(query, "profile_id")
                if profile_id is None:
                    self._error(HTTPStatus.BAD_REQUEST, "profile_id is required")
                    return
                try:
                    result = profile_store.analyze_audio(
                        recording_session.snapshot(),
                        recording_session.sample_rate,
                        profile_id,
                    )
                    self._learning_response(result, saved=False)
                except Exception as exc:
                    self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return

            if parsed.path == "/api/learn":
                profile_id = _required_query(query, "profile_id")
                if profile_id is None:
                    self._error(HTTPStatus.BAD_REQUEST, "profile_id is required")
                    return
                try:
                    result = profile_store.learn_audio(
                        recording_session.snapshot(),
                        recording_session.sample_rate,
                        profile_id,
                        accept_review=_query_bool(query, "accept_review"),
                        overwrite=_query_bool(query, "overwrite"),
                    )
                    self._learning_response(result, saved=True)
                except Exception as exc:
                    self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return

            if parsed.path == "/api/import":
                profile_id = _required_query(query, "profile_id")
                body = self._read_body()
                if body is None:
                    return
                with tempfile.NamedTemporaryFile(
                    suffix=".yaml", delete=False
                ) as temporary:
                    temporary.write(body)
                    temporary_path = Path(temporary.name)
                try:
                    destination = profile_store.import_profile(
                        temporary_path,
                        profile_id=profile_id,
                        overwrite=_query_bool(query, "overwrite"),
                    )
                    self._json(
                        {
                            "saved": True,
                            "profile_id": destination.stem,
                            "path": str(destination),
                        },
                        status=HTTPStatus.CREATED,
                    )
                except Exception as exc:
                    self._error(HTTPStatus.BAD_REQUEST, str(exc))
                finally:
                    temporary_path.unlink(missing_ok=True)
                return

            self._error(HTTPStatus.NOT_FOUND, "Unknown API endpoint")

        def do_DELETE(self) -> None:  # noqa: N802 - stdlib handler API
            if not self._client_allowed():
                return
            parsed = urlsplit(self.path)
            if not parsed.path.startswith("/api/profiles/"):
                self._error(HTTPStatus.NOT_FOUND, "Unknown API endpoint")
                return
            profile_id = unquote(parsed.path.removeprefix("/api/profiles/"))
            current = active_profile() if active_profile is not None else None
            if current and current.get("profile_id") == profile_id:
                self._error(
                    HTTPStatus.CONFLICT,
                    "Activate a different profile before deleting this one",
                )
                return
            try:
                deleted = profile_store.delete(profile_id)
            except ValueError as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self._json(
                {"deleted": deleted, "profile_id": profile_id},
                status=HTTPStatus.OK if deleted else HTTPStatus.NOT_FOUND,
            )

        def log_message(self, format: str, *args) -> None:
            logger.debug("Profile UI: " + format, *args)

        def _client_allowed(self) -> bool:
            client = self.client_address[0]
            if client in allowed_clients:
                return True
            logger.warning("Rejected non-ingress profile UI client: %s", client)
            self._error(HTTPStatus.FORBIDDEN, "Ingress access only")
            return False

        def _learning_response(self, result, *, saved: bool) -> None:
            payload = result.as_dict()
            payload["saved"] = saved
            payload["yaml"] = profile_to_yaml(result.profile)
            self._json(
                payload,
                status=HTTPStatus.CREATED if saved else HTTPStatus.OK,
            )

        def _read_body(self) -> bytes | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._error(HTTPStatus.BAD_REQUEST, "Invalid Content-Length")
                return None
            if length <= 0:
                self._error(HTTPStatus.BAD_REQUEST, "Request body is empty")
                return None
            if length > MAX_IMPORT_BYTES:
                self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Import is too large")
                return None
            return self.rfile.read(length)

        def _serve_static(self, request_path: str) -> None:
            relative = (
                "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
            )
            candidate = (static_root / relative).resolve()
            root = static_root.resolve()
            if root not in candidate.parents and candidate != root:
                self._error(HTTPStatus.FORBIDDEN, "Invalid path")
                return
            if not candidate.is_file():
                self._error(HTTPStatus.NOT_FOUND, "File not found")
                return
            content_type = {
                ".html": "text/html; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8",
                ".svg": "image/svg+xml",
            }.get(candidate.suffix.lower(), "application/octet-stream")
            self._send(candidate.read_bytes(), content_type)

        def _json(self, payload, *, status: HTTPStatus = HTTPStatus.OK) -> None:
            self._send(
                json.dumps(payload, indent=2).encode("utf-8"),
                "application/json; charset=utf-8",
                status=status,
            )

        def _text(self, text: str, content_type: str) -> None:
            self._send(text.encode("utf-8"), content_type)

        def _error(self, status: HTTPStatus, message: str) -> None:
            self._json({"error": message}, status=status)

        def _send(
            self,
            body: bytes,
            content_type: str,
            *,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def _required_query(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values or not values[0].strip():
        return None
    return values[0].strip()


def _query_bool(query: dict[str, list[str]], key: str) -> bool:
    values = query.get(key)
    return bool(values and values[0].lower() in {"1", "true", "yes", "on"})
