from __future__ import annotations

from detector.ha_bridge import HABridge


class FakeClient:
    def __init__(self) -> None:
        self.connected = False
        self.started = False
        self.discovered = False
        self.disconnected = False
        self.updates: list[tuple[str, str, bool, bool]] = []
        self.options = None

    def connect(self) -> bool:
        self.connected = True
        return True

    def start(self) -> None:
        self.started = True

    def publish_discovery(self) -> bool:
        self.discovered = True
        return True

    def update_state(
        self,
        name: str,
        device_class: str,
        state: bool,
        *,
        removed: bool = False,
    ) -> bool:
        self.updates.append((name, device_class, state, removed))
        return True

    def status(self) -> dict[str, object]:
        return {"connected": self.connected, "pending_updates": 0}

    def update_addon_options(self, options) -> bool:
        self.options = dict(options)
        return True

    def disconnect(self) -> None:
        self.disconnected = True


class FakeTimer:
    instances: list["FakeTimer"] = []

    def __init__(self, interval, function, args=()) -> None:
        self.interval = interval
        self.function = function
        self.args = args
        self.daemon = False
        self.started = False
        self.cancelled = False
        self.instances.append(self)

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        self.function(*self.args)


def test_setup_and_detection_never_call_http_directly() -> None:
    FakeTimer.instances.clear()
    client = FakeClient()
    bridge = HABridge(
        {"Smoke Alarm": "smoke"},
        hold_seconds=4,
        client=client,
        timer_factory=FakeTimer,
    )

    assert bridge.setup() is True
    assert client.started is True
    assert client.discovered is True
    assert client.updates == [("Smoke Alarm", "smoke", False, False)]

    bridge.on_detection("Smoke Alarm")
    assert client.updates[-1] == ("Smoke Alarm", "smoke", True, False)
    timer = FakeTimer.instances[-1]
    assert timer.interval == 4
    assert timer.started is True

    timer.fire()
    assert client.updates[-1] == ("Smoke Alarm", "smoke", False, False)


def test_repeated_detection_rearms_one_clear_timer() -> None:
    FakeTimer.instances.clear()
    client = FakeClient()
    bridge = HABridge(
        {"Washer": "running"},
        client=client,
        timer_factory=FakeTimer,
    )
    bridge.setup()

    bridge.on_detection("Washer")
    first = FakeTimer.instances[-1]
    bridge.on_detection("Washer")
    second = FakeTimer.instances[-1]

    assert first.cancelled is True
    assert second.started is True
    assert client.updates.count(("Washer", "running", True, False)) == 1


def test_reconfigure_and_status_use_same_publisher() -> None:
    client = FakeClient()
    bridge = HABridge({"Smoke": "smoke"}, client=client)
    bridge.setup()

    bridge.reconfigure({"CO": "carbon_monoxide"})
    assert client.updates[-2:] == [
        ("Smoke", "smoke", False, True),
        ("CO", "carbon_monoxide", False, False),
    ]
    assert bridge.status()["detectors"] == [
        {"name": "CO", "device_class": "carbon_monoxide"}
    ]

    options = {"detectors": [{"name": "CO", "preset": "co_t4"}]}
    assert bridge.persist_options(options) is True
    assert client.options == options

    bridge.shutdown()
    assert client.disconnected is True
