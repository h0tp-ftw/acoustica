"""Canonical profile learning and storage built on acoustic-engine."""

from __future__ import annotations

import math
import os
import re
import wave
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np
import yaml
from acoustic_engine.learn import learn_profile_from_audio
from acoustic_engine.models import AlarmProfile
from acoustic_engine.profiles import (
    load_profile_from_yaml,
    save_profile_to_yaml,
    validate_profile,
)

DEFAULT_PROFILE_DIR = Path("/data/profiles")
_PROFILE_ID_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class RecordingMetrics:
    """Simple recording quality measurements without a second DSP pipeline."""

    duration_seconds: float
    sample_rate: int
    peak_ratio: float
    rms_ratio: float
    clipping_ratio: float


@dataclass(frozen=True, slots=True)
class LearningResult:
    """Learned canonical profile plus plain-language quality feedback."""

    profile_id: str
    profile: AlarmProfile
    quality: str
    messages: tuple[str, ...]
    metrics: RecordingMetrics

    def as_dict(self) -> dict[str, object]:
        tone_count = sum(segment.type == "tone" for segment in self.profile.segments)
        return {
            "profile_id": self.profile_id,
            "quality": self.quality,
            "messages": list(self.messages),
            "metrics": asdict(self.metrics),
            "profile": {
                "name": self.profile.name,
                "segment_count": len(self.profile.segments),
                "tone_count": tone_count,
                "confirmation_cycles": self.profile.confirmation_cycles,
                "reset_timeout": self.profile.reset_timeout,
            },
        }


@dataclass(frozen=True, slots=True)
class ProfileSummary:
    profile_id: str
    segment_count: int
    tone_count: int
    confirmation_cycles: int
    reset_timeout: float


class ProfileStore:
    """Store only validated acoustic-engine YAML profiles."""

    def __init__(self, root: str | Path | None = None) -> None:
        configured = root if root is not None else os.getenv("PROFILE_DIR")
        self.root = Path(configured) if configured else DEFAULT_PROFILE_DIR

    def analyze(
        self,
        recording_path: str | Path,
        profile_id: str,
    ) -> LearningResult:
        """Learn and validate a profile from a WAV without writing it."""

        audio, sample_rate, _metrics = load_wav_recording(recording_path)
        return self.analyze_audio(audio, sample_rate, profile_id)

    def analyze_audio(
        self,
        audio: np.ndarray,
        sample_rate: int,
        profile_id: str,
    ) -> LearningResult:
        """Learn from the add-on's captured mono int16 audio stream."""

        normalized_id = normalize_profile_id(profile_id)
        metrics = measure_recording(audio, sample_rate)
        profile = learn_profile_from_audio(
            audio,
            sample_rate,
            name=normalized_id,
        )
        validate_profile(profile)

        return LearningResult(
            profile_id=normalized_id,
            profile=profile,
            quality=_quality_level(metrics, profile),
            messages=_quality_messages(metrics, profile),
            metrics=metrics,
        )

    def learn(
        self,
        recording_path: str | Path,
        profile_id: str,
        *,
        overwrite: bool = False,
        accept_review: bool = False,
    ) -> LearningResult:
        """Analyze a WAV and save only an approved, usable profile."""

        result = self.analyze(recording_path, profile_id)
        return self.save_learning(
            result,
            overwrite=overwrite,
            accept_review=accept_review,
        )

    def learn_audio(
        self,
        audio: np.ndarray,
        sample_rate: int,
        profile_id: str,
        *,
        overwrite: bool = False,
        accept_review: bool = False,
    ) -> LearningResult:
        """Analyze live captured audio and save only after quality approval."""

        result = self.analyze_audio(audio, sample_rate, profile_id)
        return self.save_learning(
            result,
            overwrite=overwrite,
            accept_review=accept_review,
        )

    def save_learning(
        self,
        result: LearningResult,
        *,
        overwrite: bool = False,
        accept_review: bool = False,
    ) -> LearningResult:
        """Approve and save a prior learning result."""

        if result.quality == "poor":
            raise ValueError(" ".join(result.messages))
        if result.quality == "review" and not accept_review:
            raise ValueError(
                "The recording needs review before saving. "
                + " ".join(result.messages)
            )

        self.save(result.profile_id, result.profile, overwrite=overwrite)
        return result

    def save(
        self,
        profile_id: str,
        profile: AlarmProfile,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Validate and atomically save one profile."""

        normalized_id = normalize_profile_id(profile_id)
        canonical_profile = replace(profile, name=normalized_id)
        validate_profile(canonical_profile)

        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.path_for(normalized_id)
        if destination.exists() and not overwrite:
            raise FileExistsError(
                f"Profile '{normalized_id}' already exists. Choose another ID or overwrite it."
            )

        temporary = destination.with_suffix(".yaml.tmp")
        try:
            save_profile_to_yaml(canonical_profile, temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    def load(self, profile_id: str) -> AlarmProfile:
        """Load and validate one stored profile."""

        normalized_id = normalize_profile_id(profile_id)
        profile = load_profile_from_yaml(self.path_for(normalized_id))
        validate_profile(profile)
        if profile.name != normalized_id:
            raise ValueError(
                f"Profile file '{normalized_id}.yaml' declares name "
                f"'{profile.name}'. Save or import it through ProfileStore so IDs match."
            )
        return profile

    def import_profile(
        self,
        source: str | Path,
        *,
        profile_id: str | None = None,
        overwrite: bool = False,
    ) -> Path:
        """Import a canonical engine YAML profile into add-on-owned storage."""

        profile = load_profile_from_yaml(source)
        validate_profile(profile)
        destination_id = profile_id or profile.name
        return self.save(destination_id, profile, overwrite=overwrite)

    def list(self) -> list[ProfileSummary]:
        """List all readable profiles in stable order."""

        if not self.root.exists():
            return []

        summaries: list[ProfileSummary] = []
        for path in sorted(self.root.glob("*.yaml")):
            profile = self.load(path.stem)
            summaries.append(
                ProfileSummary(
                    profile_id=path.stem,
                    segment_count=len(profile.segments),
                    tone_count=sum(
                        segment.type == "tone" for segment in profile.segments
                    ),
                    confirmation_cycles=profile.confirmation_cycles,
                    reset_timeout=profile.reset_timeout,
                )
            )
        return summaries

    def delete(self, profile_id: str) -> bool:
        """Delete one stored profile and report whether it existed."""

        path = self.path_for(profile_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def path_for(self, profile_id: str) -> Path:
        return self.root / f"{normalize_profile_id(profile_id)}.yaml"


def profile_to_dict(profile: AlarmProfile) -> dict[str, object]:
    """Serialize the public engine model into its canonical YAML shape."""

    data: dict[str, object] = {
        "name": profile.name,
        "confirmation_cycles": profile.confirmation_cycles,
        "reset_timeout": profile.reset_timeout,
    }
    if profile.resolution is not None:
        data["resolution"] = {
            "min_tone_duration": profile.resolution.min_tone_duration,
            "dropout_tolerance": profile.resolution.dropout_tolerance,
        }

    segments: list[dict[str, object]] = []
    for segment in profile.segments:
        item: dict[str, object] = {
            "type": segment.type,
            "duration": {
                "min": segment.duration.min,
                "max": segment.duration.max,
            },
        }
        if segment.type == "tone" and segment.frequency is not None:
            item["frequency"] = {
                "min": segment.frequency.min,
                "max": segment.frequency.max,
            }
            item["min_magnitude"] = segment.min_magnitude
        segments.append(item)
    data["segments"] = segments
    return data


def profile_to_yaml(profile: AlarmProfile) -> str:
    """Return canonical, human-readable YAML for a validated profile."""

    validate_profile(profile)
    return yaml.safe_dump(profile_to_dict(profile), sort_keys=False)


def normalize_profile_id(value: str) -> str:
    """Convert a user-facing label into a safe stable profile ID."""

    normalized = _PROFILE_ID_PATTERN.sub("_", value.strip().lower()).strip("_")
    if not normalized:
        raise ValueError("Profile ID must contain at least one letter or number")
    return normalized


def load_wav_recording(
    path: str | Path,
) -> tuple[np.ndarray, int, RecordingMetrics]:
    """Load 16/32-bit PCM WAV audio as mono int16 and calculate quality metrics."""

    recording_path = Path(path)
    try:
        with wave.open(str(recording_path), "rb") as recording:
            sample_rate = recording.getframerate()
            channels = recording.getnchannels()
            sample_width = recording.getsampwidth()
            frame_count = recording.getnframes()
            raw = recording.readframes(frame_count)
    except (FileNotFoundError, wave.Error) as exc:
        raise ValueError(f"Could not read WAV recording: {exc}") from exc

    if sample_width == 2:
        audio = np.frombuffer(raw, dtype=np.int16)
    elif sample_width == 4:
        int32_audio = np.frombuffer(raw, dtype=np.int32)
        audio = (int32_audio.astype(np.float64) / 2147483648.0 * 32767).astype(
            np.int16
        )
    else:
        raise ValueError("Recording must be 16-bit or 32-bit PCM WAV")

    if channels < 1:
        raise ValueError("Recording has no audio channels")
    if channels > 1:
        if len(audio) % channels:
            raise ValueError("Recording contains an incomplete audio frame")
        audio = audio.reshape(-1, channels).mean(axis=1).astype(np.int16)

    return audio, sample_rate, measure_recording(audio, sample_rate)


def measure_recording(audio: np.ndarray, sample_rate: int) -> RecordingMetrics:
    """Measure a mono recording captured from the production audio stream."""

    if sample_rate <= 0:
        raise ValueError("Sample rate must be positive")
    if audio.dtype != np.int16:
        audio = np.asarray(audio, dtype=np.int16)

    float_audio = audio.astype(np.float64) / 32768.0
    absolute = np.abs(float_audio)
    duration = len(audio) / sample_rate
    peak = float(absolute.max()) if absolute.size else 0.0
    rms = float(math.sqrt(np.mean(float_audio**2))) if float_audio.size else 0.0
    clipping = float(np.mean(absolute >= 0.99)) if absolute.size else 0.0

    return RecordingMetrics(
        duration_seconds=round(duration, 3),
        sample_rate=sample_rate,
        peak_ratio=round(peak, 4),
        rms_ratio=round(rms, 4),
        clipping_ratio=round(clipping, 6),
    )


def _quality_messages(
    metrics: RecordingMetrics, profile: AlarmProfile
) -> tuple[str, ...]:
    messages: list[str] = []
    tone_count = sum(segment.type == "tone" for segment in profile.segments)

    if metrics.duration_seconds < 2.0:
        messages.append("Record a longer sample with at least two complete alarm cycles.")
    if metrics.peak_ratio < 0.08:
        messages.append("The microphone is too quiet. Move it closer and record again.")
    if metrics.clipping_ratio > 0.005:
        messages.append("The recording clipped. Lower the microphone gain and retry.")
    if tone_count < 2:
        messages.append("Only one clear tone was learned. Capture more of the pattern.")

    if not messages:
        messages.append(
            f"Strong sample — learned a repeating cycle with {tone_count} clear tones."
        )
    return tuple(messages)


def _quality_level(metrics: RecordingMetrics, profile: AlarmProfile) -> str:
    tone_count = sum(segment.type == "tone" for segment in profile.segments)
    if metrics.peak_ratio < 0.02 or metrics.clipping_ratio > 0.03 or tone_count == 0:
        return "poor"
    if (
        metrics.duration_seconds < 2.0
        or metrics.peak_ratio < 0.08
        or metrics.clipping_ratio > 0.005
        or tone_count < 2
    ):
        return "review"
    return "strong"
