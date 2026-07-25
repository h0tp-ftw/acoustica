from __future__ import annotations

from acoustic_engine.config import AudioSettings
from acoustic_engine.events import PatternMatchEvent
from acoustic_engine.models import AlarmProfile, Range, Segment

from detector.detector import PatternDetector


class FakeTimer:
    instances: list["FakeTimer"] = []

    def __init__(self, interval, function) -> None:
        self.interval = interval
        self.function = function
        self.cancelled = False
        self.started = False
        self.daemon = False
        self.instances.append(self)

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        if not self.cancelled:
            self.function()


def _profile() -> AlarmProfile:
    return AlarmProfile(
        name="smoke",
        confirmation_cycles=1,
        reset_timeout=5.0,
        segments=[
            Segment(
                type="tone",
                frequency=Range(3000, 3400),
                duration=Range(0.4, 0.7),
            )
        ],
    )


def _match(timestamp: float = 1.0) -> PatternMatchEvent:
    return PatternMatchEvent(
        timestamp=timestamp,
        duration=1.0,
        profile_name="smoke",
        cycle_count=1,
    )


def test_later_match_extends_clear_deadline() -> None:
    FakeTimer.instances.clear()
    states: list[bool] = []
    detector = PatternDetector(
        profile=_profile(),
        audio_config=AudioSettings(),
        on_detection=states.append,
        timer_factory=FakeTimer,
    )

    detector._handle_match(_match(1.0))
    first_timer = FakeTimer.instances[-1]
    detector._handle_match(_match(2.0))
    second_timer = FakeTimer.instances[-1]

    assert states == [True]
    assert first_timer.cancelled is True
    assert second_timer.interval == 5.0

    first_timer.fire()
    assert states == [True]
    assert detector.alarm_active is True

    second_timer.fire()
    assert states == [True, False]
    assert detector.alarm_active is False


def test_close_cancels_timer_and_publishes_clear_once() -> None:
    FakeTimer.instances.clear()
    states: list[bool] = []
    detector = PatternDetector(
        profile=_profile(),
        audio_config=AudioSettings(),
        on_detection=states.append,
        timer_factory=FakeTimer,
    )

    detector._handle_match(_match())
    timer = FakeTimer.instances[-1]
    detector.close()
    detector.close()

    assert timer.cancelled is True
    assert states == [True, False]
