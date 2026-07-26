from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml
from acoustic_engine.models import AlarmProfile, Range, Segment

from detector import setup_service, tuner_server


def _profile(name: str = "Kitchen Timer") -> AlarmProfile:
    return AlarmProfile(
        name=name,
        confirmation_cycles=2,
        segments=[
            Segment(
                type="tone",
                frequency=Range(950, 1050),
                duration=Range(0.3, 0.5),
            ),
            Segment(type="silence", duration=Range(0.15, 0.3)),
        ],
    )


def test_audio_level_gives_plain_language_guidance() -> None:
    silent = setup_service.audio_level(np.zeros(44100, dtype=np.int16))
    assert silent["status"] == "silent"
    assert "microphone" in str(silent["message"]).lower()

    tone = (np.sin(np.linspace(0, 50, 44100)) * 8000).astype(np.int16)
    good = setup_service.audio_level(tone)
    assert good["status"] == "good"
    assert 0 < good["meter"] <= 100


def test_tolerance_choices_are_non_cumulative_and_human_scaled() -> None:
    base = _profile()
    forgiving = setup_service.apply_tolerance(base, "forgiving")
    precise = setup_service.apply_tolerance(base, "precise")

    assert base.confirmation_cycles == 2
    assert forgiving.confirmation_cycles == 1
    assert precise.confirmation_cycles == 3
    assert forgiving.segments[0].frequency.min < base.segments[0].frequency.min
    assert precise.segments[0].frequency.min > base.segments[0].frequency.min
    assert forgiving.segments[0].duration.max > precise.segments[0].duration.max


def test_profile_yaml_is_canonical_and_atomic(tmp_path: Path) -> None:
    profile = _profile("Front Door Chime")
    yaml_text = setup_service.profile_to_yaml(profile)
    parsed = yaml.safe_load(yaml_text)

    assert parsed["name"] == "Front Door Chime"
    assert parsed["segments"][0]["frequency"] == {"min": 950.0, "max": 1050.0}

    path = tmp_path / "front_door_chime.yaml"
    setup_service.atomic_save_profile(profile, path)
    assert path.read_text(encoding="utf-8") == yaml_text
    assert not list(tmp_path.glob("*.tmp"))


def test_microphone_check_uses_current_runtime_device(monkeypatch) -> None:
    samples = (np.sin(np.linspace(0, 20, 44100)) * 9000).astype(np.int16)
    calls = []
    monkeypatch.setattr(tuner_server, "_current_audio_settings", lambda: (44100, 7))
    monkeypatch.setattr(
        tuner_server,
        "_record_audio",
        lambda seconds, sample_rate, device: calls.append(
            (seconds, sample_rate, device)
        )
        or samples,
    )

    result = tuner_server.setup_microphone_check(
        tuner_server.MicrophoneCheckRequest(seconds=2)
    )

    assert calls == [(2, 44100, 7)]
    assert result["status"] == "good"
    assert result["device_index"] == 7


def test_learn_endpoint_returns_editable_profile(monkeypatch) -> None:
    monkeypatch.setattr(tuner_server, "_current_audio_settings", lambda: (44100, None))
    monkeypatch.setattr(
        tuner_server,
        "_record_audio",
        lambda *_args: (np.sin(np.linspace(0, 20, 44100)) * 9000).astype(np.int16),
    )
    monkeypatch.setattr(tuner_server, "learn_profile", lambda *_args, **_kwargs: _profile("Dryer Done"))

    result = tuner_server.setup_learn_sound(
        tuner_server.LearnSoundRequest(
            name="Dryer Done",
            seconds=8,
            tolerance="balanced",
        )
    )

    assert yaml.safe_load(result["profile_yaml"])["name"] == "Dryer Done"
    assert result["summary"]["tones_per_pattern"] == 1
    assert result["tolerance"] == "balanced"


def test_fresh_test_returns_actionable_result(monkeypatch) -> None:
    monkeypatch.setattr(tuner_server, "_current_audio_settings", lambda: (44100, 2))
    monkeypatch.setattr(
        tuner_server,
        "_record_audio",
        lambda *_args: (np.sin(np.linspace(0, 20, 44100)) * 9000).astype(np.int16),
    )
    monkeypatch.setattr(
        tuner_server.engine_tuner,
        "run_engine_pipeline",
        lambda *_args: {
            "detections": [{"profile_name": "Kitchen Timer"}],
            "tone_events": [{"frequency": 1000}],
        },
    )

    result = tuner_server.setup_test_sound(
        tuner_server.TestSoundRequest(
            profile_yaml=setup_service.profile_to_yaml(_profile()),
            seconds=6,
        )
    )

    assert result["detected"] is True
    assert result["guidance"]["code"] == "matched"
    assert result["detection_count"] == 1


def test_save_and_enable_rolls_back_profile_on_runtime_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ACOUSTIC_PROFILES_DIR", str(tmp_path))
    path = tmp_path / "kitchen_timer.yaml"
    path.write_text("original profile", encoding="utf-8")

    def fail_runtime(*_args, **_kwargs):
        raise tuner_server.HTTPException(status_code=503, detail="runtime offline")

    monkeypatch.setattr(tuner_server, "_runtime_request", fail_runtime)

    with pytest.raises(tuner_server.HTTPException):
        tuner_server.setup_save_and_enable(
            tuner_server.SaveAndEnableRequest(
                name="Kitchen Timer",
                profile_yaml=setup_service.profile_to_yaml(_profile()),
                device_class="sound",
            )
        )

    assert path.read_text(encoding="utf-8") == "original profile"


def test_save_and_enable_activates_atomic_profile(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ACOUSTIC_PROFILES_DIR", str(tmp_path))
    calls = []
    monkeypatch.setattr(
        tuner_server,
        "_runtime_request",
        lambda method, path, payload=None: calls.append((method, path, payload))
        or {"reloaded": True},
    )

    result = tuner_server.setup_save_and_enable(
        tuner_server.SaveAndEnableRequest(
            name="Front Door Chime",
            profile_yaml=setup_service.profile_to_yaml(_profile()),
            device_class="sound",
        )
    )

    saved = tmp_path / "front_door_chime.yaml"
    assert saved.is_file()
    assert yaml.safe_load(saved.read_text(encoding="utf-8"))["name"] == "Front Door Chime"
    assert calls[-1] == (
        "POST",
        "/activate",
        {"profile_id": "front_door_chime", "device_class": "sound"},
    )
    assert result["runtime"]["reloaded"] is True
