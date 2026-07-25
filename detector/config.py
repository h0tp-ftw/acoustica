"""Runtime configuration backed by acoustic-engine's canonical profile model."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from acoustic_engine.config import AudioSettings
from acoustic_engine.models import AlarmProfile, Range, Segment

from .profile_service import ProfileStore

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DetectorConfig:
    """Configuration required by the add-on runtime."""

    device_name: str
    alarm_type: str
    profile_id: str
    audio: AudioSettings
    profiles: list[AlarmProfile]
    debug_mode: bool = False

    @classmethod
    def from_environment(cls) -> "DetectorConfig":
        """Build a canonical engine profile from Home Assistant options."""

        alarm_type = os.getenv("ALARM_TYPE", "smoke").strip().lower()
        if alarm_type not in {"smoke", "co", "safety"}:
            raise ValueError(f"Unsupported alarm category: {alarm_type!r}")

        audio = AudioSettings(
            sample_rate=_env_int("SAMPLE_RATE", 44100, minimum=8000),
            chunk_size=_env_int("CHUNK_SIZE", 1024, minimum=128),
            channels=1,
            device_index=_optional_env_int("AUDIO_DEVICE_INDEX"),
        )

        requested_profile_id = os.getenv("PROFILE_ID", "").strip()
        if requested_profile_id:
            profile = ProfileStore().load(requested_profile_id)
            profile_id = profile.name
        else:
            if alarm_type == "safety":
                raise ValueError(
                    "The safety category requires a learned profile_id"
                )
            profile = _build_profile(alarm_type)
            profile_id = profile.name

        return cls(
            device_name=os.getenv("DEVICE_NAME", "smoke_alarm_detector").strip()
            or "smoke_alarm_detector",
            alarm_type=alarm_type,
            profile_id=profile_id,
            audio=audio,
            profiles=[profile],
            debug_mode=_env_bool("DEBUG_MODE", False),
        )

    def log_config(self) -> None:
        """Log a compact, actionable startup summary."""

        logger.info(
            "Device: %s | Category: %s | Profile: %s",
            self.device_name,
            self.alarm_type,
            self.profile_id,
        )
        logger.info(
            "Audio: %s Hz, chunk=%s, device=%s",
            self.audio.sample_rate,
            self.audio.chunk_size,
            self.audio.device_index if self.audio.device_index is not None else "default",
        )
        for profile in self.profiles:
            logger.info(
                "Profile: %s (%s segments, %s confirmation cycles, %.1fs clear timeout)",
                profile.name,
                len(profile.segments),
                profile.confirmation_cycles,
                profile.reset_timeout,
            )


def _build_profile(alarm_type: str) -> AlarmProfile:
    """Create one T3/T4 profile using the engine's public schema."""

    beep_count = 4 if alarm_type == "co" else 3
    target_frequency = _env_float("TARGET_FREQ", 3133.0, minimum=100.0)
    frequency_tolerance = _env_float("FREQ_TOLERANCE", 250.0, minimum=1.0)
    magnitude = _env_float("MIN_MAGNITUDE", 0.05, minimum=0.0)

    if alarm_type == "co":
        beep_min_default, beep_max_default = 0.08, 0.20
        pause_min_default, pause_max_default = 0.05, 0.20
        final_pause = Range(3.0, 6.0)
        name = "co"
    else:
        beep_min_default, beep_max_default = 0.40, 0.70
        pause_min_default, pause_max_default = 0.30, 0.70
        final_pause = Range(1.0, 1.8)
        name = "smoke"

    beep_duration = _ordered_range(
        _env_float("BEEP_MIN", beep_min_default, minimum=0.01),
        _env_float("BEEP_MAX", beep_max_default, minimum=0.01),
        "beep duration",
    )
    pause_duration = _ordered_range(
        _env_float("PAUSE_MIN", pause_min_default, minimum=0.01),
        _env_float("PAUSE_MAX", pause_max_default, minimum=0.01),
        "pause duration",
    )
    frequency = Range(
        max(1.0, target_frequency - frequency_tolerance),
        target_frequency + frequency_tolerance,
    )

    segments: list[Segment] = []
    for index in range(beep_count):
        segments.append(
            Segment(
                type="tone",
                frequency=frequency,
                duration=beep_duration,
                min_magnitude=magnitude,
            )
        )
        segments.append(
            Segment(
                type="silence",
                duration=final_pause if index == beep_count - 1 else pause_duration,
            )
        )

    return AlarmProfile(
        name=name,
        segments=segments,
        confirmation_cycles=_env_int("CONFIRMATION_CYCLES", 2, minimum=1),
        reset_timeout=_env_float("RESET_TIMEOUT", 10.0, minimum=0.1),
    )


def _ordered_range(minimum: float, maximum: float, label: str) -> Range:
    if minimum > maximum:
        raise ValueError(f"Minimum {label} cannot exceed maximum {label}")
    return Range(minimum, maximum)


def _env_bool(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int, *, minimum: int | None = None) -> int:
    value = os.getenv(key)
    result = default if value is None or not value.strip() else int(value)
    if minimum is not None and result < minimum:
        raise ValueError(f"{key} must be at least {minimum}")
    return result


def _optional_env_int(key: str) -> int | None:
    value = os.getenv(key)
    if value is None or not value.strip():
        return None
    result = int(value)
    return None if result < 0 else result


def _env_float(key: str, default: float, *, minimum: float | None = None) -> float:
    value = os.getenv(key)
    result = default if value is None or not value.strip() else float(value)
    if minimum is not None and result < minimum:
        raise ValueError(f"{key} must be at least {minimum}")
    return result
