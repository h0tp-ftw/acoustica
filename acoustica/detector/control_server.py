"""Local-only control API used by the ingress tuner process."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

StatusCallback = Callable[[], dict[str, object]]
ActivateCallback = Callable[[str, str], dict[str, object]]
AudioCallback = Callable[[int | None], dict[str, object]]


class ControlServer:
    """Expose runtime controls only on the container loopback interface."""

    def __init__(
        self,
        *,
        status: StatusCallback,
        activate_profile: ActivateCallback,
        select_audio_device: AudioCallback,
        host: str = "127.0.0.1",
        port: int = 8100,
    ) -> None:
        self.host = host
        self.port = port
        self._status = status
        self._activate_profile = activate_profile
        self._select_audio_device = select_audio_device
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        if self._server is not None:
            return True
        handler = _handler_factory(
            self._status,
            self._activate_profile,
            self._select_audio_device,
        )
        try:
            self._server = ThreadingHTTPServer((self.host, self.port), handler)
        except OSError as exc:
            logger.error("Could not start runtime control server: %s", exc)
            return False
        self.port = self._server.server_port
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="runtime-control",
            daemon=True,
        )
        self._thread.start()
        logger.info("Runtime control API listening on %s:%s", self.host, self.port)
        return True

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._thread = None
        self._server = None


def _handler_factory(
    status: StatusCallback,
    activate_profile: ActivateCallback,
    select_audio_device: AudioCallback,
):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AcousticaControl/1"

        def do_GET(self) -> None:  # noqa: N802
            if urlsplit(self.path).path != "/status":
                self._error(HTTPStatus.NOT_FOUND, "Unknown endpoint")
                return
            self._json(status())

        def do_POST(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            try:
                body = self._read_json()
                if path == "/activate":
                    profile_id = body.get("profile_id")
                    device_class = body.get("device_class", "sound")
                    if not isinstance(profile_id, str) or not profile_id.strip():
                        raise ValueError("profile_id is required")
                    if not isinstance(device_class, str) or not device_class.strip():
                        raise ValueError("device_class is required")
                    self._json(activate_profile(profile_id, device_class))
                    return
                if path == "/audio/select":
                    raw_index = body.get("device_index")
                    if raw_index in (None, -1):
                        device_index = None
                    elif isinstance(raw_index, int):
                        device_index = raw_index
                    else:
                        raise ValueError("device_index must be an integer or null")
                    self._json(select_audio_device(device_index))
                    return
                self._error(HTTPStatus.NOT_FOUND, "Unknown endpoint")
            except (ValueError, RuntimeError) as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception as exc:  # pragma: no cover - defensive boundary
                logger.exception("Runtime control request failed")
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("Request body must be valid JSON") from exc
            if not isinstance(parsed, dict):
                raise ValueError("Request body must be a JSON object")
            return parsed

        def _json(self, payload: dict[str, object], status_code: int = 200) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _error(self, status: HTTPStatus, message: str) -> None:
            self._json({"error": message}, int(status))

        def log_message(self, format: str, *args) -> None:
            logger.debug("control: " + format, *args)

    return Handler
