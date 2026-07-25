from __future__ import annotations

import pytest

from detector.config import DetectorConfig
from detector.profile_service import ProfileStore
from detector.yaml_loader import load_profile_from_yaml


_ENV_KEYS = (
    "DEVICE_NAME",
    "ALARM_TYPE",
    "PROFILE_ID",
    "PROFILE_DIR",
    "TARGET_FREQ",
    "FREQ_TOLERANCE",
    "MIN_MAGNITUDE",
    "BEEP_MIN",
    "BEEP_MAX",
    "PAUSE_MIN",
    "PAUSE_MAX",
    "CONFIRMATION_CYCLES",
    "RESET_TIMEOUT",
    "SAMPLE_RATE",
    "CHUNK_SIZE",
    "AUDIO_DEVICE_INDEX",
    "DEBUG_MODE",
)


def _clear_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_smoke_profile_uses_canonical_engine_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_environment(monkeypatch)

    config = DetectorConfig.from_environment()
    profile = config.profiles[0]

    assert config.profile_id == "smoke"
    assert profile.name == "smoke"
    assert profile.confirmation_cycles == 2
    assert profile.reset_timeout == 10.0
    assert [segment.type for segment in profile.segments] == [
        "tone",
        "silence",
        "tone",
        "silence",
        "tone",
        "silence",
    ]
    assert profile.segments[-1].duration.min == 1.0
    assert profile.segments[-1].duration.max == 1.8


def test_co_profile_uses_t4_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("ALARM_TYPE", "co")

    profile = DetectorConfig.from_environment().profiles[0]

    assert profile.name == "co"
    assert len(profile.segments) == 8
    assert profile.segments[0].duration.min == 0.08
    assert profile.segments[-1].duration.min == 3.0


def test_learned_profile_is_loaded_directly_from_addon_storage(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _clear_environment(monkeypatch)
    profile = load_profile_from_yaml("profiles/smoke_alarm_t3.yaml")
    store = ProfileStore(tmp_path)
    store.save("hallway_alarm", profile)

    monkeypatch.setenv("PROFILE_DIR", str(tmp_path))
    monkeypatch.setenv("PROFILE_ID", "hallway_alarm")
    monkeypatch.setenv("ALARM_TYPE", "safety")

    config = DetectorConfig.from_environment()

    assert config.profile_id == "hallway_alarm"
    assert config.alarm_type == "safety"
    assert config.profiles[0].name == "hallway_alarm"
    assert config.profiles[0] == store.load("hallway_alarm")


def test_safety_category_requires_a_learned_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("ALARM_TYPE", "safety")

    with pytest.raises(ValueError, match="requires a learned profile_id"):
        DetectorConfig.from_environment()


def test_audio_device_minus_one_uses_default_and_positive_index_is_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("AUDIO_DEVICE_INDEX", "-1")
    assert DetectorConfig.from_environment().audio.device_index is None

    monkeypatch.setenv("AUDIO_DEVICE_INDEX", "4")
    assert DetectorConfig.from_environment().audio.device_index == 4


def test_invalid_duration_range_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("BEEP_MIN", "0.8")
    monkeypatch.setenv("BEEP_MAX", "0.2")

    with pytest.raises(ValueError, match="Minimum beep duration"):
        DetectorConfig.from_environment()
