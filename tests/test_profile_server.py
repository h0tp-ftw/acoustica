from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pytest

from detector.addon_control import AudioDeviceService
from detector.profile_server import ProfileServer, ProfileTestSession
from detector.profile_service import ProfileStore

SAMPLE_RATE = 44100


class FakeRestartTimer:
    instances: list["FakeRestartTimer"] = []

    def __init__(self, interval, function) -> None:
        self.interval = interval
        self.function = function
        self.daemon = False
        self.started = False
        self.instances.append(self)

    def start(self) -> None:
        self.started = True

    def fire(self) -> None:
        self.function()


def _tone(duration: float, frequency: float) -> np.ndarray:
    count = round(SAMPLE_RATE * duration)
    timeline = np.arange(count, dtype=np.float64) / SAMPLE_RATE
    return (0.7 * np.sin(2 * np.pi * frequency * timeline) * 32767).astype(
        np.int16
    )


def _silence(duration: float) -> np.ndarray:
    return np.zeros(round(SAMPLE_RATE * duration), dtype=np.int16)


def _smoke_audio() -> np.ndarray:
    chunks = [_silence(0.5)]
    for _ in range(3):
        for index in range(3):
            chunks.append(_tone(0.5, 3150))
            chunks.append(_silence(1.4 if index == 2 else 0.5))
    return np.concatenate(chunks)


def _preset_test_audio() -> np.ndarray:
    chunks = [_silence(0.5)]
    for _ in range(3):
        chunks.extend(
            [
                _tone(0.5, 3050),
                _silence(0.5),
                _tone(0.5, 3050),
                _silence(0.5),
                _tone(0.5, 3050),
                _silence(1.4),
            ]
        )
    # A following tone closes the final long-silence event in the stream parser.
    chunks.extend([_tone(0.5, 3050), _silence(1.0)])
    return np.concatenate(chunks)


def _json(url: str) -> dict | list:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read())


def _post(url: str, body: bytes | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        data=b"" if body is None else body,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.status, json.loads(response.read())


def test_profile_server_guided_learning_flow(tmp_path: Path) -> None:
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<h1>Profile setup</h1>", encoding="utf-8")

    store = ProfileStore(tmp_path / "profiles")
    server = ProfileServer(
        sample_rate=SAMPLE_RATE,
        host="127.0.0.1",
        port=0,
        profile_store=store,
        static_root=static,
        allowed_clients={"127.0.0.1"},
    )
    assert server.start() is True
    base = f"http://127.0.0.1:{server.port}"

    try:
        health = _json(f"{base}/api/health")
        assert health["status"] == "ok"
        assert health["profiles"] == 0
        assert health["recording"]["has_recording"] is False

        status, started = _post(f"{base}/api/record/start")
        assert status == 200
        assert started["recording"] is True

        audio = _smoke_audio()
        for offset in range(0, len(audio), 1024):
            server.feed(audio[offset : offset + 1024])

        recording = _json(f"{base}/api/record/status")
        assert recording["has_recording"] is True
        assert recording["duration_seconds"] > 5

        status, stopped = _post(f"{base}/api/record/stop")
        assert status == 200
        assert stopped["recording"] is False

        status, analysis = _post(
            f"{base}/api/analyze?profile_id=hallway_alarm"
        )
        assert status == 200
        assert analysis["saved"] is False
        assert analysis["quality"] == "strong"
        assert "name: hallway_alarm" in analysis["yaml"]
        assert store.list() == []

        status, learned = _post(f"{base}/api/learn?profile_id=hallway_alarm")
        assert status == 201
        assert learned["saved"] is True
        assert store.load("hallway_alarm").name == "hallway_alarm"

        profiles = _json(f"{base}/api/profiles")
        assert profiles[0]["profile_id"] == "hallway_alarm"

        status, test_started = _post(
            f"{base}/api/test/start?profile_id=hallway_alarm"
        )
        assert status == 200
        assert test_started["testing"] is True
        assert test_started["matched"] is False

        for offset in range(0, len(audio), 1024):
            server.feed(audio[offset : offset + 1024])

        test_status = _json(f"{base}/api/test/status")
        assert test_status["matched"] is True
        assert test_status["match_count"] >= 1

        status, test_stopped = _post(f"{base}/api/test/stop")
        assert status == 200
        assert test_stopped["testing"] is False
        assert test_stopped["matched"] is True

        request = urllib.request.Request(
            f"{base}/api/profiles/hallway_alarm",
            method="DELETE",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            deleted = json.loads(response.read())
        assert deleted["deleted"] is True
        assert store.list() == []

        with urllib.request.urlopen(base, timeout=5) as response:
            assert b"Profile setup" in response.read()
    finally:
        server.stop()


def test_microphone_api_persists_selection_and_schedules_restart(tmp_path: Path) -> None:
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<h1>Profile setup</h1>", encoding="utf-8")
    persisted: list[int | None] = []
    restarts: list[bool] = []
    FakeRestartTimer.instances.clear()
    audio_devices = AudioDeviceService(
        None,
        persist_device=lambda index: persisted.append(index) or True,
        restart_addon=lambda: restarts.append(True) or True,
        device_lister=lambda: [
            {
                "index": 4,
                "name": "USB Microphone",
                "channels": 1,
                "default": True,
                "backend": "sounddevice",
            }
        ],
        timer_factory=FakeRestartTimer,
    )
    server = ProfileServer(
        sample_rate=SAMPLE_RATE,
        host="127.0.0.1",
        port=0,
        profile_store=ProfileStore(tmp_path / "profiles"),
        audio_device_service=audio_devices,
        static_root=static,
        allowed_clients={"127.0.0.1"},
    )
    assert server.start() is True
    base = f"http://127.0.0.1:{server.port}"

    try:
        status = _json(f"{base}/api/audio/devices")
        assert status["current_index"] is None
        assert status["devices"][0]["name"] == "USB Microphone"

        code, selected = _post(f"{base}/api/audio/select?device_index=4")
        assert code == 200
        assert selected["saved"] is True
        assert selected["current_index"] == 4
        assert persisted == [4]

        deadline = time.monotonic() + 1.0
        while not FakeRestartTimer.instances and time.monotonic() < deadline:
            time.sleep(0.01)
        timer = FakeRestartTimer.instances[-1]
        assert timer.started is True
        assert timer.daemon is True
        assert restarts == []
        timer.fire()
        assert restarts == [True]
    finally:
        server.stop()


def test_profile_activation_endpoint_and_active_delete_guard(tmp_path: Path) -> None:
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<h1>Profile setup</h1>", encoding="utf-8")

    store = ProfileStore(tmp_path / "profiles")
    store.import_profile(
        "profiles/smoke_alarm_t3.yaml",
        profile_id="hallway_alarm",
    )
    active = {
        "ready": True,
        "device_name": "hallway_listener",
        "profile_id": "smoke",
        "alarm_type": "smoke",
    }
    activation_calls: list[tuple[str, str]] = []

    def activate(profile_id: str, alarm_type: str) -> dict[str, object]:
        activation_calls.append((profile_id, alarm_type))
        active.update(profile_id=profile_id, alarm_type=alarm_type)
        return {"activated": True, **active}

    server = ProfileServer(
        sample_rate=SAMPLE_RATE,
        host="127.0.0.1",
        port=0,
        profile_store=store,
        activate_profile=activate,
        active_profile=lambda: dict(active),
        runtime_status=lambda: {
            "ready": True,
            "listening": True,
            "detectors": [{"profile_id": active["profile_id"], "active": False}],
            "last_detection": None,
            "home_assistant": {"connected": True, "pending_updates": 0},
        },
        static_root=static,
        allowed_clients={"127.0.0.1"},
    )
    assert server.start() is True
    base = f"http://127.0.0.1:{server.port}"

    try:
        status, activated = _post(
            f"{base}/api/profiles/hallway_alarm/activate?alarm_type=smoke"
        )
        assert status == 200
        assert activated["activated"] is True
        assert activated["profile_id"] == "hallway_alarm"
        assert activation_calls == [("hallway_alarm", "smoke")]
        health = _json(f"{base}/api/health")
        assert health["active_profile"] == active
        assert health["runtime"]["listening"] is True
        assert health["runtime"]["home_assistant"]["connected"] is True

        request = urllib.request.Request(
            f"{base}/api/profiles/hallway_alarm",
            method="DELETE",
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=5)
        assert error.value.code == 409
        assert store.load("hallway_alarm").name == "hallway_alarm"

        active["profile_id"] = "smoke"
        with urllib.request.urlopen(request, timeout=5) as response:
            deleted = json.loads(response.read())
        assert deleted["deleted"] is True
    finally:
        server.stop()


def test_saved_profile_can_be_live_tested_without_state_publisher(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles")
    store.import_profile(
        "profiles/smoke_alarm_t3.yaml",
        profile_id="smoke_test",
    )
    session = ProfileTestSession(
        store,
        SAMPLE_RATE,
        1024,
        max_seconds=30,
    )

    started = session.start("smoke_test")
    assert started["testing"] is True

    audio = _preset_test_audio()
    for offset in range(0, len(audio), 1024):
        chunk = audio[offset : offset + 1024]
        if len(chunk) < 1024:
            chunk = np.pad(chunk, (0, 1024 - len(chunk)))
        session.feed(chunk)

    status = session.status()
    assert status["matched"] is True
    assert status["match_count"] >= 1
    session.stop()


def test_recording_session_is_bounded(tmp_path: Path) -> None:
    server = ProfileServer(
        sample_rate=100,
        host="127.0.0.1",
        port=0,
        profile_store=ProfileStore(tmp_path),
        static_root=tmp_path,
        allowed_clients={"127.0.0.1"},
    )
    server.recording_session.max_samples = 10
    server.recording_session.start()
    server.feed(np.arange(25, dtype=np.int16))

    status = server.recording_session.status()
    assert status["recording"] is False
    assert len(server.recording_session.snapshot()) == 10
