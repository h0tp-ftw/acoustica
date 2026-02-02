#!/usr/bin/env python3
"""Quick integration test for the windowed matcher."""

import sys

sys.path.insert(0, "src")

from acoustic_engine.analysis.event_buffer import EventBuffer
from acoustic_engine.events import ToneEvent
from acoustic_engine.profiles import load_profiles_from_yaml
from acoustic_engine.analysis.windowed_matcher import WindowedMatcher


def test_basic_imports():
    """Test that all new components import correctly."""
    print("✓ EventBuffer imported")
    print("✓ WindowedMatcher imported")
    print("✓ All imports OK!")


def test_event_buffer():
    """Test EventBuffer functionality."""
    buf = EventBuffer(max_duration=10.0)

    # Add some events
    buf.add(ToneEvent(timestamp=1.0, duration=0.5, frequency=3000, magnitude=0.8))
    buf.add(ToneEvent(timestamp=2.0, duration=0.5, frequency=3000, magnitude=0.8))
    buf.add(ToneEvent(timestamp=3.0, duration=0.5, frequency=3000, magnitude=0.8))

    assert len(buf) == 3, f"Expected 3 events, got {len(buf)}"
    print("✓ EventBuffer basic operations work")

    # Test windowing
    events = buf.get_window(3.5, 2.0)  # Get events from 1.5 to 3.5
    assert len(events) == 2, f"Expected 2 events in window, got {len(events)}"
    print("✓ EventBuffer windowing works")


def test_windowed_matcher():
    """Test WindowedMatcher with smoke alarm profile."""
    profiles = load_profiles_from_yaml("profiles/smoke_alarm_t3.yaml")
    print(f"✓ Loaded profile: {profiles[0].name}")

    matcher = WindowedMatcher(profiles)
    print("✓ WindowedMatcher initialized")
    print(f"  Window config: duration={matcher.configs[profiles[0].name].window_duration:.1f}s")
    print(f"  Eval frequency: {matcher.configs[profiles[0].name].eval_frequency:.2f}s")

    # Simulate some tone events (3 beeps for T3 pattern)
    matcher.add_event(ToneEvent(timestamp=0.5, duration=0.5, frequency=3000, magnitude=0.8))
    matcher.add_event(ToneEvent(timestamp=1.2, duration=0.5, frequency=3000, magnitude=0.8))
    matcher.add_event(ToneEvent(timestamp=1.9, duration=0.5, frequency=3000, magnitude=0.8))
    # Second cycle
    matcher.add_event(ToneEvent(timestamp=3.0, duration=0.5, frequency=3000, magnitude=0.8))
    matcher.add_event(ToneEvent(timestamp=3.7, duration=0.5, frequency=3000, magnitude=0.8))
    matcher.add_event(ToneEvent(timestamp=4.4, duration=0.5, frequency=3000, magnitude=0.8))

    print("✓ Added 6 events (2 T3 cycles)")

    # Evaluate
    matches = matcher.evaluate(5.0)
    print(f"  Matches found: {len(matches)}")

    print("✓ WindowedMatcher evaluation completed")


def test_engine_with_windowed_matcher():
    """Test that Engine uses WindowedMatcher."""
    from acoustic_engine.engine import Engine
    from acoustic_engine.analysis.windowed_matcher import WindowedMatcher

    profiles = load_profiles_from_yaml("profiles/smoke_alarm_t3.yaml")
    engine = Engine(profiles=profiles)

    assert isinstance(engine._matcher, WindowedMatcher), "Engine should use WindowedMatcher"
    print("✓ Engine correctly uses WindowedMatcher")


def main():
    print("=" * 50)
    print("Windowed Matcher Integration Tests")
    print("=" * 50)
    print()

    test_basic_imports()
    print()

    test_event_buffer()
    print()

    test_windowed_matcher()
    print()

    test_engine_with_windowed_matcher()
    print()

    print("=" * 50)
    print("All tests passed! ✓")
    print("=" * 50)


if __name__ == "__main__":
    main()
