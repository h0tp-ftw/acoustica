"""Deterministic end-to-end tests through the published engine pipeline."""

from __future__ import annotations

import numpy as np
import pytest

from detector.config import DetectorConfig
from detector.detector import PatternDetector


class PassiveTimer:
    def __init__(self, interval, function) -> None:
        self.interval = interval
        self.function = function
        self.daemon = False
        self.cancelled = False

    def start(self) -> None:
        return None

    def cancel(self) -> None:
        self.cancelled = True


def _tone(sample_rate: int, duration: float, frequency: float) -> np.ndarray:
    sample_count = round(sample_rate * duration)
    timeline = np.arange(sample_count, dtype=np.float64) / sample_rate
    return (0.8 * np.sin(2 * np.pi * frequency * timeline) * 32767).astype(
        np.int16
    )


def _silence(sample_rate: int, duration: float) -> np.ndarray:
    return np.zeros(round(sample_rate * duration), dtype=np.int16)


def _synthesize_profile(profile, sample_rate: int, cycles: int) -> np.ndarray:
    chunks = [_silence(sample_rate, 0.5)]
    for _ in range(cycles):
        for segment in profile.segments:
            duration = (segment.duration.min + segment.duration.max) / 2
            if segment.type == "tone":
                frequency = (segment.frequency.min + segment.frequency.max) / 2
                chunks.append(_tone(sample_rate, duration, frequency))
            else:
                chunks.append(_silence(sample_rate, duration))
    chunks.append(_silence(sample_rate, 1.0))
    return np.concatenate(chunks)


@pytest.mark.parametrize("alarm_type", ["smoke", "co"])
def test_synthetic_alarm_patterns_are_detected(monkeypatch, alarm_type: str) -> None:
    monkeypatch.setenv("ALARM_TYPE", alarm_type)
    monkeypatch.setenv("SAMPLE_RATE", "8000")
    monkeypatch.setenv("CHUNK_SIZE", "256")
    monkeypatch.setenv("CONFIRMATION_CYCLES", "2")

    config = DetectorConfig.from_environment()
    profile = config.profiles[0]
    states: list[bool] = []
    detector = PatternDetector(
        profile=profile,
        audio_config=config.audio,
        on_detection=states.append,
        timer_factory=PassiveTimer,
    )
    audio = _synthesize_profile(profile, config.audio.sample_rate, cycles=3)

    chunk_size = config.audio.chunk_size
    remainder = len(audio) % chunk_size
    if remainder:
        audio = np.pad(audio, (0, chunk_size - remainder))

    detected = False
    for offset in range(0, len(audio), chunk_size):
        detected = detector.process(audio[offset : offset + chunk_size]) or detected

    assert detected is True
    assert states == [True]
    detector.close()
    assert states == [True, False]
