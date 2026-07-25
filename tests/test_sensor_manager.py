from __future__ import annotations

from detector.sensor import SensorManager


class FakeClient:
    def __init__(self, connected: bool = True) -> None:
        self.connected_result = connected
        self.connect_calls = 0
        self.started = False
        self.disconnected = False
        self.restart_calls = 0
        self.discoveries: list[str] = []
        self.updates: list[tuple[str, bool]] = []

    def connect(self) -> bool:
        self.connect_calls += 1
        return self.connected_result

    def start(self) -> None:
        self.started = True

    def publish_discovery(self, profile_id: str) -> bool:
        self.discoveries.append(profile_id)
        return True

    def update_state(self, profile_id: str, active: bool) -> bool:
        self.updates.append((profile_id, active))
        return True

    def status(self) -> dict[str, object]:
        return {
            "connected": self.connected_result,
            "pending_updates": 0,
            "published_profiles": len(self.updates),
            "discovery_published": bool(self.discoveries),
        }

    def restart_addon(self) -> bool:
        self.restart_calls += 1
        return True

    def disconnect(self) -> None:
        self.disconnected = True


def test_setup_uses_one_client_and_publishes_initial_clear_states() -> None:
    client = FakeClient()
    manager = SensorManager(
        device_name="hallway",
        profile_names=["smoke", "co"],
        alarm_type="smoke",
        client=client,
    )

    assert manager.setup() is True
    assert client.connect_calls == 1
    assert client.started is True
    assert client.discoveries == ["smoke"]
    assert client.updates == [("smoke", False), ("co", False)]


def test_detection_callback_routes_only_known_profile() -> None:
    client = FakeClient()
    manager = SensorManager(
        "hallway",
        ["smoke"],
        "smoke",
        client=client,
    )

    callback = manager.create_detection_callback("smoke")
    callback(True)

    assert client.updates == [("smoke", True)]
    assert manager.update_state("unknown", True) is False
    assert client.updates == [("smoke", True)]


def test_status_uses_the_same_client() -> None:
    client = FakeClient()
    manager = SensorManager("hallway", ["smoke"], "smoke", client=client)

    assert manager.status()["connected"] is True


def test_restart_uses_the_same_client() -> None:
    client = FakeClient()
    manager = SensorManager("hallway", ["smoke"], "smoke", client=client)

    assert manager.restart_addon() is True
    assert client.restart_calls == 1


def test_setup_continues_with_background_delivery_when_probe_fails() -> None:
    client = FakeClient(connected=False)
    manager = SensorManager(
        "hallway",
        ["smoke"],
        "smoke",
        client=client,
    )

    assert manager.setup() is False
    assert client.started is True
    assert client.discoveries == ["smoke"]
    assert client.updates == [("smoke", False)]

    manager.cleanup()
    assert client.disconnected is True
