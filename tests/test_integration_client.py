from __future__ import annotations

import json
import urllib.error
from datetime import UTC, datetime

from detector import __version__
from detector.integration_client import (
    DISCOVERY_SERVICE,
    EVENT_STATE_UPDATE,
    PROTOCOL_VERSION,
    IntegrationClient,
)


class FakeResponse:
    def __init__(self, status: int = 200, body: bytes = b"") -> None:
        self.status = status
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


class FakeUrlOpen:
    def __init__(self) -> None:
        self.requests = []
        self.fail = False
        self.response_body = b""

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        if self.fail:
            raise urllib.error.URLError("offline")
        return FakeResponse(body=self.response_body)


def _client(opener: FakeUrlOpen) -> IntegrationClient:
    return IntegrationClient(
        detector_id="hallway_listener",
        alarm_type="smoke",
        token="test-token",
        urlopen=opener,
        clock=lambda: datetime(2026, 7, 25, 12, 0, tzinfo=UTC),
    )


def test_connect_uses_supervisor_core_proxy() -> None:
    opener = FakeUrlOpen()
    client = _client(opener)

    assert client.connect() is True

    request, timeout = opener.requests[-1]
    assert request.full_url == "http://supervisor/core/api/config"
    assert request.get_method() == "GET"
    assert request.headers["Authorization"] == "Bearer test-token"
    assert timeout == 5


def test_discovery_uses_supervisor_pipeline_and_stable_service() -> None:
    opener = FakeUrlOpen()
    opener.response_body = json.dumps(
        {"result": "ok", "data": {"uuid": "discovery-uuid"}}
    ).encode()
    client = _client(opener)

    assert client.publish_discovery("hallway_alarm") is True
    assert client.discovery_uuid == "discovery-uuid"

    request, timeout = opener.requests[-1]
    assert request.full_url == "http://supervisor/discovery"
    assert request.get_method() == "POST"
    assert timeout == 5
    assert json.loads(request.data) == {
        "service": DISCOVERY_SERVICE,
        "config": {
            "protocol_version": PROTOCOL_VERSION,
            "detector_id": "hallway_listener",
            "profile_id": "hallway_alarm",
            "alarm_type": "smoke",
            "source_version": __version__,
        },
    }


def test_event_payload_is_versioned_and_integration_owned() -> None:
    opener = FakeUrlOpen()
    client = _client(opener)

    assert client.update_state("smoke", True) is True
    assert client.pending_count == 1
    assert client.latest_count == 1
    assert client._publish_pending_once() is True
    assert client.pending_count == 0

    request, _timeout = opener.requests[-1]
    payload = json.loads(request.data)

    assert request.full_url.endswith(f"/events/{EVENT_STATE_UPDATE}")
    assert "/states/" not in request.full_url
    assert payload == {
        "protocol_version": PROTOCOL_VERSION,
        "detector_id": "hallway_listener",
        "profile_id": "smoke",
        "alarm_type": "smoke",
        "active": True,
        "updated_at": "2026-07-25T12:00:00+00:00",
        "source_version": __version__,
    }


def test_status_exposes_only_delivery_health() -> None:
    opener = FakeUrlOpen()
    client = _client(opener)
    client.update_state("smoke", True)

    assert client.status() == {
        "connected": False,
        "pending_updates": 1,
        "published_profiles": 1,
        "discovery_published": False,
    }

    assert client._publish_pending_once() is True
    assert client.status()["connected"] is True
    assert client.status()["pending_updates"] == 0


def test_newer_state_replaces_older_unsent_state() -> None:
    opener = FakeUrlOpen()
    client = _client(opener)

    client.update_state("smoke", True)
    client.update_state("smoke", False)

    assert client.pending_count == 1
    assert client._publish_pending_once() is True
    payload = json.loads(opener.requests[-1][0].data)
    assert payload["active"] is False


def test_failed_heartbeat_moves_latest_snapshot_back_to_retry_queue() -> None:
    opener = FakeUrlOpen()
    client = _client(opener)

    client.update_state("co", True)
    assert client._publish_pending_once() is True
    assert client.pending_count == 0

    opener.fail = True
    assert client._publish_latest_once() is False
    assert client.pending_count == 1

    opener.fail = False
    assert client._publish_pending_once() is True
    assert client.pending_count == 0


def test_supervisor_self_options_and_restart_use_one_authenticated_client() -> None:
    opener = FakeUrlOpen()
    client = _client(opener)
    options = {
        "alarm_type": "smoke",
        "profile_id": "hallway_alarm",
        "audio_device_index": 5,
    }

    assert client.update_addon_options(options) is True
    options_request, options_timeout = opener.requests[-1]
    assert options_request.full_url == "http://supervisor/addons/self/options"
    assert options_request.get_method() == "POST"
    assert json.loads(options_request.data) == {"options": options}
    assert options_timeout == 10

    assert client.restart_addon() is True
    restart_request, restart_timeout = opener.requests[-1]
    assert restart_request.full_url == "http://supervisor/addons/self/restart"
    assert restart_request.get_method() == "POST"
    assert json.loads(restart_request.data) == {}
    assert restart_timeout == 5


def test_missing_token_never_starts_or_queues() -> None:
    client = IntegrationClient(
        detector_id="hallway",
        alarm_type="smoke",
        token="",
    )

    client.start()

    assert client.connect() is False
    assert client.update_state("smoke", True) is False
    assert client.pending_count == 0
