from __future__ import annotations

import pytest

from detector.addon_control import AudioDeviceService


class FakeTimer:
    instances: list["FakeTimer"] = []

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


def _devices() -> list[dict]:
    return [
        {
            "index": 2,
            "name": "USB Microphone",
            "channels": 1,
            "default": True,
            "backend": "sounddevice",
        },
        {
            "index": 5,
            "name": "Webcam Mic",
            "channels": 2,
            "default": False,
            "backend": "sounddevice",
        },
    ]


def test_device_selection_validates_persists_and_restarts_later() -> None:
    persisted: list[int | None] = []
    restarts: list[bool] = []
    FakeTimer.instances.clear()
    service = AudioDeviceService(
        None,
        persist_device=lambda index: persisted.append(index) or True,
        restart_addon=lambda: restarts.append(True) or True,
        device_lister=_devices,
        timer_factory=FakeTimer,
    )

    status = service.select(5)

    assert status["current_index"] == 5
    assert status["devices"][0]["name"] == "USB Microphone"
    assert persisted == [5]

    service.schedule_restart(0.5)
    timer = FakeTimer.instances[-1]
    assert timer.interval == 0.5
    assert timer.daemon is True
    assert timer.started is True
    assert restarts == []

    timer.fire()
    assert restarts == [True]


def test_default_device_and_unknown_index() -> None:
    persisted: list[int | None] = []
    service = AudioDeviceService(
        2,
        persist_device=lambda index: persisted.append(index) or True,
        restart_addon=lambda: True,
        device_lister=_devices,
    )

    assert service.select(None)["current_index"] is None
    assert persisted == [None]

    with pytest.raises(ValueError, match="not available"):
        service.select(99)
