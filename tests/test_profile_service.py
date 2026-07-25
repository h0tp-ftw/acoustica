from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from detector.profile_service import (
    ProfileStore,
    load_wav_recording,
    normalize_profile_id,
)


def _tone(sample_rate: int, duration: float, frequency: float, amplitude: float) -> np.ndarray:
    sample_count = round(sample_rate * duration)
    timeline = np.arange(sample_count, dtype=np.float64) / sample_rate
    return (amplitude * np.sin(2 * np.pi * frequency * timeline) * 32767).astype(
        np.int16
    )


def _silence(sample_rate: int, duration: float) -> np.ndarray:
    return np.zeros(round(sample_rate * duration), dtype=np.int16)


def _write_smoke_recording(
    path: Path,
    *,
    amplitude: float = 0.7,
    cycles: int = 3,
) -> None:
    sample_rate = 44100
    chunks = [_silence(sample_rate, 0.5)]
    for _ in range(cycles):
        for tone_index in range(3):
            chunks.append(_tone(sample_rate, 0.5, 3150, amplitude))
            chunks.append(
                _silence(sample_rate, 1.4 if tone_index == 2 else 0.5)
            )
    chunks.append(_silence(sample_rate, 0.5))
    audio = np.concatenate(chunks)

    with wave.open(str(path), "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(sample_rate)
        recording.writeframes(audio.tobytes())


def test_profile_id_is_safe_and_stable() -> None:
    assert normalize_profile_id(" Hallway Smoke Alarm ") == "hallway_smoke_alarm"
    assert normalize_profile_id("CO-Alarm #2") == "co_alarm_2"
    with pytest.raises(ValueError):
        normalize_profile_id("---")


def test_learned_profile_uses_engine_schema_and_round_trips(tmp_path: Path) -> None:
    recording = tmp_path / "smoke.wav"
    _write_smoke_recording(recording)
    store = ProfileStore(tmp_path / "profiles")

    result = store.learn(recording, "Hallway Smoke Alarm")
    restored = store.load("hallway_smoke_alarm")

    assert result.profile_id == "hallway_smoke_alarm"
    assert result.profile.name == "hallway_smoke_alarm"
    assert result.quality == "strong"
    assert sum(segment.type == "tone" for segment in result.profile.segments) == 3
    assert restored == result.profile
    assert store.list()[0].profile_id == "hallway_smoke_alarm"


def test_quiet_recording_gets_plain_language_review_feedback(tmp_path: Path) -> None:
    recording = tmp_path / "quiet.wav"
    _write_smoke_recording(recording, amplitude=0.04)
    store = ProfileStore(tmp_path / "profiles")

    result = store.analyze(recording, "quiet_alarm")

    assert result.quality == "review"
    assert any("too quiet" in message for message in result.messages)
    assert not store.path_for("quiet_alarm").exists()

    with pytest.raises(ValueError, match="needs review"):
        store.learn(recording, "quiet_alarm")

    accepted = store.learn(recording, "quiet_alarm", accept_review=True)
    assert accepted.profile_id == "quiet_alarm"
    assert store.path_for("quiet_alarm").exists()


def test_existing_profile_requires_explicit_overwrite(tmp_path: Path) -> None:
    recording = tmp_path / "smoke.wav"
    _write_smoke_recording(recording)
    store = ProfileStore(tmp_path / "profiles")

    store.learn(recording, "smoke")
    with pytest.raises(FileExistsError):
        store.learn(recording, "smoke")

    overwritten = store.learn(recording, "smoke", overwrite=True)
    assert overwritten.profile_id == "smoke"


def test_imported_profile_is_normalized_into_addon_storage(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles")

    destination = store.import_profile(
        "profiles/smoke_alarm_t3.yaml",
        profile_id="Imported Smoke",
    )

    assert destination.name == "imported_smoke.yaml"
    assert store.load("imported_smoke").name == "imported_smoke"


def test_wav_metrics_detect_clipping(tmp_path: Path) -> None:
    path = tmp_path / "clipped.wav"
    audio = np.full(44100, 32767, dtype=np.int16)
    with wave.open(str(path), "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(44100)
        recording.writeframes(audio.tobytes())

    _audio, _sample_rate, metrics = load_wav_recording(path)

    assert metrics.duration_seconds == 1.0
    assert metrics.peak_ratio > 0.99
    assert metrics.clipping_ratio == 1.0
