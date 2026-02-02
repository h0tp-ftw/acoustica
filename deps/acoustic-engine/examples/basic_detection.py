#!/usr/bin/env python3
"""Example: Basic alarm detection.

This example shows how to use the Acoustic Alarm Engine to detect
alarm patterns from microphone input.
"""

import logging
import sys
from pathlib import Path

# Add src to path to allow running without installation
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from acoustic_engine import AudioConfig, Engine
from acoustic_engine.profiles import load_profiles_from_yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%H:%M:%S"
)


def on_alarm_detected(profile_name: str):
    """Callback when an alarm is detected."""
    print(f"\n🚨 ALARM DETECTED: {profile_name}\n")
    # Here you could:
    # - Send a notification
    # - Trigger home automation
    # - Log to a file
    # - etc.


def main():
    # Load alarm profiles
    profiles = load_profiles_from_yaml("../profiles/smoke_alarm_t3.yaml")
    print(f"Loaded {len(profiles)} profile(s)")

    # Create the engine
    engine = Engine(
        profiles=profiles,
        audio_config=AudioConfig(
            sample_rate=44100,
            chunk_size=4096,
        ),
        on_detection=on_alarm_detected,
    )

    print("🎤 Starting audio capture...")
    print("   Press Ctrl+C to stop\n")

    # Start listening (blocking)
    try:
        engine.start()
    except KeyboardInterrupt:
        print("\n👋 Stopping...")
        engine.stop()


if __name__ == "__main__":
    main()
