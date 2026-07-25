from __future__ import annotations

import json

import pytest

from detector.main import DetectorApp
from detector.profile_service import ProfileStore


class FakeSensorManager:
    instances: list["FakeSensorManager"] = []
    persist_result = True

    def __init__(self, device_name, profile_names, alarm_type) -> None:
        self.device_name = device_name
        self.profile_names = profile_names
        self.alarm_type = alarm_type
        self.cleaned = False
        self.persisted_options = None
        self.restart_calls = 0
        self.instances.append(self)

    def setup(self) -> bool:
        return True

    def create_detection_callback(self, _profile_name):
        return lambda _state: None

    def persist_addon_options(self, options) -> bool:
        self.persisted_options = dict(options)
        return self.persist_result

    def status(self) -> dict[str, object]:
        return {
            "connected": True,
            "pending_updates": 0,
            "published_profiles": len(self.profile_names),
            "discovery_published": True,
        }

    def restart_addon(self) -> bool:
        self.restart_calls += 1
        return True

    def cleanup(self) -> None:
        self.cleaned = True


class FakeProfileServer:
    def __init__(
        self,
        sample_rate,
        chunk_size,
        activate_profile,
        active_profile,
        runtime_status,
        audio_device_service,
    ) -> None:
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.activate_profile = activate_profile
        self.active_profile = active_profile
        self.runtime_status = runtime_status
        self.audio_device_service = audio_device_service
        self.profile_store = None
        self.started = False
        self.stopped = False
        self.chunks = []

    def start(self) -> bool:
        self.started = True
        return True

    def feed(self, chunk) -> None:
        self.chunks.append(chunk)

    def stop(self) -> None:
        self.stopped = True


class FakeDetector:
    instances: list["FakeDetector"] = []

    def __init__(self, profile, audio_config, on_detection) -> None:
        self.profile = profile
        self.name = profile.name
        self.audio_config = audio_config
        self.on_detection = on_detection
        self.alarm_active = False
        self.closed = False
        self.instances.append(self)

    def process(self, _chunk) -> bool:
        return False

    def close(self) -> None:
        self.closed = True


class FakeListener:
    setup_result = True

    def __init__(self, config, callback) -> None:
        self.config = config
        self.callback = callback
        self.stopped = False
        self.cleaned = False

    def setup(self) -> bool:
        return self.setup_result

    def start(self) -> None:
        return None

    def stop(self) -> None:
        self.stopped = True

    def cleanup(self) -> None:
        self.cleaned = True


def _app(
    listener_factory=FakeListener,
    *,
    options_path="/data/options.json",
) -> DetectorApp:
    FakeSensorManager.instances.clear()
    FakeDetector.instances.clear()
    FakeSensorManager.persist_result = True
    return DetectorApp(
        listener_factory=listener_factory,
        detector_factory=FakeDetector,
        sensor_manager_factory=FakeSensorManager,
        profile_server_factory=FakeProfileServer,
        options_path=options_path,
    )


def test_unexpected_audio_loop_exit_is_fatal(monkeypatch) -> None:
    monkeypatch.setenv("ALARM_TYPE", "smoke")
    monkeypatch.delenv("PROFILE_ID", raising=False)
    app = _app()

    assert app.setup() is True
    assert app.run() == 1
    assert app.listener.stopped is True
    assert app.listener.cleaned is True
    assert app.detectors[0].closed is True
    assert app.sensor_manager.cleaned is True
    assert app.profile_server.started is True
    assert app.profile_server.stopped is True


def test_audio_setup_failure_prevents_start(monkeypatch) -> None:
    monkeypatch.setenv("ALARM_TYPE", "smoke")
    monkeypatch.delenv("PROFILE_ID", raising=False)

    class FailingListener(FakeListener):
        setup_result = False

    app = _app(FailingListener)

    assert app.setup() is False
    app.cleanup()
    assert app.listener.cleaned is True


def test_runtime_status_reports_connection_and_last_detection(monkeypatch) -> None:
    monkeypatch.setenv("ALARM_TYPE", "smoke")
    monkeypatch.delenv("PROFILE_ID", raising=False)
    app = _app()

    assert app.setup() is True
    before = app.runtime_status()
    assert before["ready"] is True
    assert before["listening"] is False
    assert before["home_assistant"]["connected"] is True
    assert before["last_detection"] is None

    app.running = True
    app.detectors[0].on_detection(True)
    after = app.runtime_status()
    assert after["listening"] is True
    assert after["detectors"] == [{"profile_id": "smoke", "active": False}]
    assert after["last_detection"]["profile_id"] == "smoke"
    assert after["last_detection"]["detected_at"].endswith("+00:00")

    app.cleanup()


def test_saved_profile_activates_without_restart(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ALARM_TYPE", "smoke")
    monkeypatch.delenv("PROFILE_ID", raising=False)
    options_path = tmp_path / "options.json"
    options_path.write_text(
        json.dumps(
            {
                "device_name": "smoke_alarm_detector",
                "alarm_type": "smoke",
                "profile_id": "",
                "debug_mode": False,
            }
        ),
        encoding="utf-8",
    )

    app = _app(options_path=options_path)
    assert app.setup() is True

    store = ProfileStore(tmp_path / "profiles")
    store.import_profile(
        "profiles/smoke_alarm_t3.yaml",
        profile_id="hallway_smoke",
    )
    app.profile_server.profile_store = store
    old_detector = app.detectors[0]
    old_manager = app.sensor_manager

    result = app.activate_profile("hallway_smoke", "smoke")

    assert result["activated"] is True
    assert result["profile_id"] == "hallway_smoke"
    assert result["alarm_type"] == "smoke"
    assert app.config.profile_id == "hallway_smoke"
    assert app.detectors[0].profile.name == "hallway_smoke"
    assert app.sensor_manager is FakeSensorManager.instances[-1]
    assert app.sensor_manager.persisted_options == {
        "device_name": "smoke_alarm_detector",
        "alarm_type": "smoke",
        "profile_id": "hallway_smoke",
        "debug_mode": False,
    }
    assert old_detector.closed is True
    assert old_manager.cleaned is True

    app.cleanup()


def test_failed_option_persistence_keeps_old_runtime(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ALARM_TYPE", "smoke")
    monkeypatch.delenv("PROFILE_ID", raising=False)
    options_path = tmp_path / "options.json"
    options_path.write_text(
        json.dumps({"alarm_type": "smoke", "profile_id": ""}),
        encoding="utf-8",
    )

    app = _app(options_path=options_path)
    assert app.setup() is True
    store = ProfileStore(tmp_path / "profiles")
    store.import_profile(
        "profiles/smoke_alarm_t3.yaml",
        profile_id="hallway_smoke",
    )
    app.profile_server.profile_store = store
    old_detector = app.detectors[0]
    old_manager = app.sensor_manager
    FakeSensorManager.persist_result = False

    with pytest.raises(RuntimeError, match="Could not save"):
        app.activate_profile("hallway_smoke", "smoke")

    assert app.detectors == [old_detector]
    assert app.sensor_manager is old_manager
    assert app.config.profile_id == "smoke"
    assert old_detector.closed is False
    assert old_manager.cleaned is False
    assert FakeDetector.instances[-1].closed is True
    assert FakeSensorManager.instances[-1].cleaned is True

    app.cleanup()
