from __future__ import annotations

import json
import signal
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from detector.control_server import ControlServer
from detector.main import DetectorApp


class FakeEngine:
    instances: list["FakeEngine"] = []
    fail_next_start = False

    def __init__(self, pipelines, audio_config, on_detection) -> None:
        self.pipelines = pipelines
        self.audio_config = audio_config
        self.on_detection = on_detection
        self.started = threading.Event()
        self.stopped = threading.Event()
        self.start_count = 0
        self._run_stop = threading.Event()
        self.fail_on_start = self.fail_next_start
        self.__class__.fail_next_start = False
        self.instances.append(self)

    def start(self) -> None:
        self.start_count += 1
        self._run_stop = threading.Event()
        self.started.set()
        if self.fail_on_start:
            raise RuntimeError("candidate audio failed after preflight")
        self._run_stop.wait(timeout=5)

    def stop(self) -> None:
        self.stopped.set()
        self._run_stop.set()


class FakeBridge:
    instances: list["FakeBridge"] = []
    persist_result = True

    def __init__(self, device_classes, hold_seconds) -> None:
        self.device_classes = dict(device_classes)
        self.hold_seconds = hold_seconds
        self.persisted = None
        self.persisted_history = []
        self.reconfigured = []
        self.shutdown_called = False
        self.detected = []
        self.instances.append(self)

    def setup(self) -> bool:
        return True

    def persist_options(self, options) -> bool:
        self.persisted = dict(options)
        self.persisted_history.append(dict(options))
        return self.persist_result

    def reconfigure(self, device_classes) -> None:
        self.device_classes = dict(device_classes)
        self.reconfigured.append(dict(device_classes))

    def on_detection(self, name: str) -> None:
        self.detected.append(name)

    def status(self) -> dict[str, object]:
        return {
            "home_assistant": {"connected": True, "pending_updates": 0},
            "active_matches": [],
        }

    def shutdown(self) -> None:
        self.shutdown_called = True


class FakeControlServer:
    def __init__(self, **callbacks) -> None:
        self.callbacks = callbacks
        self.started = False
        self.stopped = False

    def start(self) -> bool:
        self.started = True
        return True

    def stop(self) -> None:
        self.stopped = True


def _write_options(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "detectors": [
                    {
                        "name": "Smoke Alarm",
                        "preset": "smoke_t3",
                        "device_class": "smoke",
                    }
                ],
                "sample_rate": 44100,
                "device_index": -1,
                "hold_seconds": 30,
                "debug": False,
            }
        ),
        encoding="utf-8",
    )


def _app(monkeypatch, tmp_path, *, audio_probe=None) -> DetectorApp:
    FakeEngine.instances.clear()
    FakeEngine.fail_next_start = False
    FakeBridge.instances.clear()
    FakeBridge.persist_result = True
    options_path = tmp_path / "options.json"
    _write_options(options_path)
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    monkeypatch.setenv("OPTIONS_JSON", str(options_path))
    monkeypatch.setenv("ACOUSTIC_DATA_DIR", str(tmp_path))
    return DetectorApp(
        engine_factory=FakeEngine,
        bridge_factory=FakeBridge,
        control_server_factory=FakeControlServer,
        device_lister=lambda: [
            {"index": 0, "name": "Default mic", "channels": 1},
            {"index": 2, "name": "USB mic", "channels": 1},
        ],
        audio_probe=audio_probe or (lambda _settings: (True, None)),
    )


def _start_runtime(app: DetectorApp) -> threading.Thread:
    assert app.setup() is True
    thread = threading.Thread(target=app.run, daemon=True)
    thread.start()
    assert FakeEngine.instances[0].started.wait(timeout=2)
    return thread


def _stop_runtime(app: DetectorApp, thread: threading.Thread) -> None:
    app._handle_signal(signal.SIGTERM, None)
    thread.join(timeout=3)
    assert not thread.is_alive()


def _wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


def test_saved_profile_and_audio_device_hot_reload(monkeypatch, tmp_path) -> None:
    app = _app(monkeypatch, tmp_path)
    profile_path = tmp_path / "profiles" / "hallway.yaml"
    profile_path.write_text(
        "name: Hallway Alarm\n"
        "confirmation_cycles: 1\n"
        "segments:\n"
        "  - type: tone\n"
        "    frequency: {min: 2900, max: 3300}\n"
        "    duration: {min: 0.3, max: 0.7}\n",
        encoding="utf-8",
    )
    thread = _start_runtime(app)

    result = app.activate_profile("hallway", "safety")
    assert result["reloaded"] is True
    assert result["generation"] == 1
    assert FakeEngine.instances[0].stopped.is_set()
    assert FakeEngine.instances[1].started.wait(timeout=2)
    assert app.config is not None
    assert {item.profile.name for item in app.config.detectors} == {
        "Smoke Alarm",
        "Hallway Alarm",
    }
    assert FakeBridge.instances[0].persisted["detectors"][-1] == {
        "name": "Hallway Alarm",
        "profile": "hallway.yaml",
        "device_class": "safety",
    }

    result = app.select_audio_device(2)
    assert result["generation"] == 2
    assert FakeEngine.instances[2].audio_config.device_index == 2
    assert FakeEngine.instances[2].started.wait(timeout=2)

    _stop_runtime(app, thread)
    assert FakeBridge.instances[0].shutdown_called is True


def test_failed_option_persistence_keeps_current_generation(monkeypatch, tmp_path) -> None:
    app = _app(monkeypatch, tmp_path)
    thread = _start_runtime(app)
    current_engine = app.engine
    FakeBridge.persist_result = False

    with pytest.raises(RuntimeError, match="could not save"):
        app.select_audio_device(2)

    assert app.engine is current_engine
    assert app.status()["generation"] == 0
    assert current_engine.stopped.is_set() is True
    _wait_until(lambda: current_engine.start_count == 2)
    assert app.status()["state"] == "listening"
    _stop_runtime(app, thread)


def test_failed_audio_preflight_restores_current_generation(monkeypatch, tmp_path) -> None:
    app = _app(
        monkeypatch,
        tmp_path,
        audio_probe=lambda _settings: (False, "USB microphone is busy"),
    )
    thread = _start_runtime(app)
    current_engine = app.engine

    with pytest.raises(RuntimeError, match="USB microphone is busy"):
        app.select_audio_device(2)

    assert app.engine is current_engine
    assert app.status()["generation"] == 0
    assert app.status()["last_error"] == "USB microphone is busy"
    assert FakeBridge.instances[0].persisted_history == []
    _wait_until(lambda: current_engine.start_count == 2)
    _stop_runtime(app, thread)


def test_candidate_start_failure_rolls_back_options_and_engine(monkeypatch, tmp_path) -> None:
    app = _app(monkeypatch, tmp_path)
    thread = _start_runtime(app)
    original_engine = app.engine
    original_options = dict(app.config.options)
    FakeEngine.fail_next_start = True

    result = app.select_audio_device(2)
    assert result["generation"] == 1

    _wait_until(lambda: app.status()["generation"] == 2)
    assert app.engine is original_engine
    assert app.config.audio.device_index is None
    assert FakeBridge.instances[0].persisted_history[-1] == original_options
    assert "restored the previous audio generation" in app.status()["last_error"]
    _wait_until(lambda: original_engine.start_count == 2)
    _stop_runtime(app, thread)


def test_control_server_exposes_only_loopback_runtime_actions() -> None:
    activated = []
    selected = []
    server = ControlServer(
        status=lambda: {"state": "listening"},
        activate_profile=lambda profile, device_class: activated.append(
            (profile, device_class)
        )
        or {"reloaded": True},
        select_audio_device=lambda index: selected.append(index) or {"reloaded": True},
        port=0,
    )
    assert server.start() is True
    base = f"http://127.0.0.1:{server.port}"

    with urllib.request.urlopen(f"{base}/status", timeout=2) as response:
        assert json.loads(response.read()) == {"state": "listening"}

    request = urllib.request.Request(
        f"{base}/activate",
        data=json.dumps({"profile_id": "hallway", "device_class": "safety"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        assert json.loads(response.read()) == {"reloaded": True}
    assert activated == [("hallway", "safety")]

    request = urllib.request.Request(
        f"{base}/audio/select",
        data=json.dumps({"device_index": 2}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=2):
        pass
    assert selected == [2]
    server.stop()
