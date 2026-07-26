"""Beginner setup helpers built on the production acoustic-engine pipeline."""

from __future__ import annotations

import copy
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from acoustic_engine.learn import learn_profile_from_audio
from acoustic_engine.models import AlarmProfile, Range, Segment
from acoustic_engine.profiles import validate_profile

TOLERANCE_LEVELS: dict[str, tuple[float, int]] = {
    "forgiving": (1.45, 1),
    "balanced": (1.0, 2),
    "precise": (0.72, 3),
}


def audio_level(samples: np.ndarray) -> dict[str, object]:
    """Return a human-oriented microphone level assessment."""

    if samples.size == 0:
        return {
            "status": "silent",
            "label": "No sound heard",
            "rms": 0.0,
            "peak": 0.0,
            "message": "The microphone did not capture any audio.",
        }

    normalized = samples.astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(np.square(normalized))))
    peak = float(np.max(np.abs(normalized)))

    if peak < 0.004 or rms < 0.001:
        status = "silent"
        label = "No clear sound heard"
        message = "Check that the microphone is connected, selected, and not muted."
    elif peak < 0.03 or rms < 0.006:
        status = "quiet"
        label = "Very quiet"
        message = "Move the microphone closer or make the sound louder before teaching Acoustica."
    elif peak > 0.985:
        status = "clipping"
        label = "Too loud"
        message = "The recording is clipping. Move the microphone a little farther away."
    else:
        status = "good"
        label = "Microphone sounds good"
        message = "The microphone level is suitable for teaching and testing."

    return {
        "status": status,
        "label": label,
        "rms": round(rms, 5),
        "peak": round(peak, 5),
        "meter": min(100, round(max(rms * 850, peak * 100))),
        "message": message,
    }


def _scaled_range(value: Range, factor: float, *, floor: float) -> Range:
    center = (float(value.min) + float(value.max)) / 2.0
    half_width = max((float(value.max) - float(value.min)) / 2.0, floor)
    scaled = half_width * factor
    return Range(
        min=round(max(floor, center - scaled), 3),
        max=round(max(floor * 2, center + scaled), 3),
    )


def apply_tolerance(profile: AlarmProfile, level: str) -> AlarmProfile:
    """Return a copy with simple forgiving/balanced/precise matching ranges."""

    if level not in TOLERANCE_LEVELS:
        raise ValueError(f"Unknown tolerance level: {level}")
    factor, confirmation_cycles = TOLERANCE_LEVELS[level]
    tuned = copy.deepcopy(profile)
    tuned.confirmation_cycles = confirmation_cycles

    for segment in tuned.segments:
        segment.duration = _scaled_range(segment.duration, factor, floor=0.02)
        if segment.type == "tone" and segment.frequency is not None:
            segment.frequency = _scaled_range(segment.frequency, factor, floor=20.0)

    validate_profile(tuned)
    return tuned


def learn_profile(
    samples: np.ndarray,
    sample_rate: int,
    *,
    name: str,
    tolerance: str = "balanced",
) -> AlarmProfile:
    """Learn a canonical profile and apply one beginner-friendly tolerance level."""

    learned = learn_profile_from_audio(samples, sample_rate, name=name.strip())
    return apply_tolerance(learned, tolerance)


def profile_summary(profile: AlarmProfile) -> dict[str, object]:
    tones = [segment for segment in profile.segments if segment.type == "tone"]
    min_cycle = sum(float(segment.duration.min) for segment in profile.segments)
    max_cycle = sum(float(segment.duration.max) for segment in profile.segments)
    frequencies = [
        round((float(segment.frequency.min) + float(segment.frequency.max)) / 2)
        for segment in tones
        if segment.frequency is not None
    ]
    return {
        "name": profile.name,
        "tones_per_pattern": len(tones),
        "pattern_steps": len(profile.segments),
        "pattern_seconds": {
            "min": round(min_cycle, 2),
            "max": round(max_cycle, 2),
        },
        "confirmation_repeats": profile.confirmation_cycles,
        "main_frequencies_hz": frequencies[:8],
    }


def profile_to_dict(profile: AlarmProfile) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": profile.name,
        "confirmation_cycles": profile.confirmation_cycles,
        "reset_timeout": profile.reset_timeout,
        "eval_frequency": profile.eval_frequency,
    }
    if profile.window_duration is not None:
        data["window_duration"] = profile.window_duration
    if profile.resolution is not None:
        data["resolution"] = {
            "min_tone_duration": profile.resolution.min_tone_duration,
            "dropout_tolerance": profile.resolution.dropout_tolerance,
        }

    segments: list[dict[str, Any]] = []
    for segment in profile.segments:
        item: dict[str, Any] = {
            "type": segment.type,
            "duration": {
                "min": round(float(segment.duration.min), 3),
                "max": round(float(segment.duration.max), 3),
            },
        }
        if segment.type == "tone" and segment.frequency is not None:
            item["frequency"] = {
                "min": round(float(segment.frequency.min), 1),
                "max": round(float(segment.frequency.max), 1),
            }
        if not math.isclose(float(segment.min_magnitude), 0.05):
            item["min_magnitude"] = round(float(segment.min_magnitude), 4)
        segments.append(item)
    data["segments"] = segments
    return data


def profile_to_yaml(profile: AlarmProfile) -> str:
    return yaml.safe_dump(
        profile_to_dict(profile),
        sort_keys=False,
        allow_unicode=True,
        width=1000,
    )


def atomic_write_text(path: Path, text: str) -> None:
    """Atomically replace one UTF-8 text file in its destination directory."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.stem}-",
        suffix=".yaml.tmp",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            Path(temporary).unlink(missing_ok=True)
        except OSError:
            pass


def atomic_save_profile(profile: AlarmProfile, path: Path) -> None:
    """Validate and atomically replace one canonical profile file."""

    validate_profile(profile)
    atomic_write_text(path, profile_to_yaml(profile))
