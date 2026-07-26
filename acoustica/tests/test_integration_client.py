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
        token="test-token",
        urlopen=opener,
        clock=lambda: datetime(2026, 7, 25, 12, 0, tzinfo=UTC),
    )


def test_discovery_uses_scoped_supervisor_service() -> None:
    opener = FakeUrlOpen()
    opener.response_body = json.dumps(
        {"result": "ok", "data": {"uuid": "discovery-uuid"}}
    ).encode()
    client = _client(opener)

    assert client.publish_discovery() is True
    request, timeout = opener.requests[-1]
    assert request.full_url == "http://supervisor/discovery"
    assert request.get_method() == "POST"
    assert timeout == 5
    payload = json.loads(request.data)
    assert payload["service"] == DISCOVERY_SERVICE
    assert payload["config"]["protocol_version"] == PROTOCOL_VERSION
    assert payload["config"]["detector_id"] == "acoustica"


def test_state_queue_is_latest_only_and_non_blocking() -> None:
    opener = FakeUrlOpen()
    client = _client(opener)

    assert client.update_state("Smoke Alarm", "smoke", True) is True
    assert client.update_state("Smoke Alarm", "smoke", False) is True
    assert client.pending_count == 1
    assert opener.requests == []

    assert client._publish_pending_once() is True
    request, timeout = opener.requests[-1]
    assert request.full_url.endswith(f"/events/{EVENT_STATE_UPDATE}")
    assert timeout == 5
    assert json.loads(request.data) == {
        "protocol_version": PROTOCOL_VERSION,
        "detector_id": "acoustica",
        "profile_id": "Smoke Alarm",
        "device_class": "smoke",
        "active": False,
        "updated_at": "2026-07-25T12:00:00+00:00",
        "source_version": __version__,
    }
    assert client.pending_count == 0


def test_failed_state_is_retained_for_retry() -> None:
    opener = FakeUrlOpen()
    client = _client(opener)
    client.update_state("Washer", "running", True)
    opener.fail = True

    assert client._publish_pending_once() is False
    assert client.pending_count == 1

    opener.fail = False
    assert client._publish_pending_once() is True
    assert client.pending_count == 0


def test_complete_options_are_sent_without_dropping_fields() -> None:
    opener = FakeUrlOpen()
    client = _client(opener)
    options = {
        "detectors": [{"name": "Smoke", "preset": "smoke_t3"}],
        "sample_rate": 44100,
        "debug": False,
    }

    assert client.update_addon_options(options) is True
    request, timeout = opener.requests[-1]
    assert request.full_url == "http://supervisor/addons/self/options"
    assert timeout == 10
    assert json.loads(request.data) == {"options": options}
