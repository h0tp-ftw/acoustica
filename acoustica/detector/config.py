"""Build reloadable Acoustica runtime configuration from add-on options."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from acoustic_engine.config import AudioSettings
from acoustic_engine.learn import learn_profile_from_file
from acoustic_engine.models import AlarmProfile
from acoustic_engine.presets import list_presets, load_preset
from acoustic_engine.profiles import load_profiles_from_yaml, save_profile_to_yaml

logger = logging.getLogger(__name__)


def options_path() -> Path:
    return Path(os.getenv("OPTIONS_JSON", "/data/options.json"))


def data_dir() -> Path:
    return Path(os.getenv("ACOUSTIC_DATA_DIR", "/data"))


def sounds_dir() -> Path:
    return data_dir() / "sounds"


def profiles_dir() -> Path:
    return data_dir() / "profiles"


_PRESET_DEVICE_CLASS = {"smoke_t3": "smoke", "co_t4": "carbon_monoxide"}
_DEFAULT_DEVICE_CLASS = "sound"
_DEFAULT_DETECTORS = [
    {"name": "Smoke Alarm", "preset": "smoke_t3", "device_class": "smoke"},
    {"name": "CO Alarm", "preset": "co_t4", "device_class": "carbon_monoxide"},
]


@dataclass(slots=True)
class DetectorSpec:
    """One configured detector and its Home Assistant presentation metadata."""

    profile: AlarmProfile
    device_class: str
    source_kind: str
    source_value: str


@dataclass(slots=True)
class AppConfig:
    """Everything the detector runtime needs for one engine generation."""

    detectors: List[DetectorSpec]
    audio: AudioSettings
    hold_seconds: float
    debug: bool
    options: dict[str, object]

    @property
    def profiles(self) -> List[AlarmProfile]:
        return [detector.profile for detector in self.detectors]

    @property
    def device_classes(self) -> dict[str, str]:
        return {
            detector.profile.name: detector.device_class
            for detector in self.detectors
        }


def read_options() -> dict[str, object]:
    """Read the complete Supervisor options object, falling back to defaults."""

    path = options_path()
    if not path.exists():
        logger.warning("No options at %s; using built-in defaults", path)
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError) as exc:
        logger.error("Could not read %s (%s); using built-in defaults", path, exc)
        return {}
    if not isinstance(parsed, dict):
        logger.error("Options at %s are not an object; using defaults", path)
        return {}
    return parsed


def _resolve(name: str, *search_dirs: Path) -> Optional[Path]:
    candidate = Path(name)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    for base in search_dirs:
        path = base / name
        if path.exists():
            return path
    return None


def _device_class_for(entry: dict[str, Any], default: str) -> str:
    value = entry.get("device_class")
    return str(value) if value else default


def _profiles_from_entry(entry: dict[str, Any]) -> List[DetectorSpec]:
    name = str(entry.get("name") or "").strip()

    if entry.get("preset"):
        preset = str(entry["preset"]).strip()
        try:
            profile = load_preset(preset)
        except KeyError:
            logger.error(
                "Detector '%s': unknown preset '%s'. Available: %s. Skipping",
                name or preset,
                preset,
                ", ".join(list_presets()),
            )
            return []
        if name:
            profile.name = name
        return [
            DetectorSpec(
                profile=profile,
                device_class=_device_class_for(
                    entry,
                    _PRESET_DEVICE_CLASS.get(preset, _DEFAULT_DEVICE_CLASS),
                ),
                source_kind="preset",
                source_value=preset,
            )
        ]

    if entry.get("profile"):
        profile_ref = str(entry["profile"]).strip()
        path = _resolve(profile_ref, profiles_dir(), data_dir())
        if path is None:
            logger.error("Detector '%s': profile '%s' was not found", name or profile_ref, profile_ref)
            return []
        try:
            profiles = load_profiles_from_yaml(path)
        except Exception as exc:
            logger.error("Detector '%s': could not load %s (%s)", name or path, path, exc)
            return []
        device_class = _device_class_for(entry, _DEFAULT_DEVICE_CLASS)
        if len(profiles) == 1 and name:
            profiles[0].name = name
        elif len(profiles) > 1 and name:
            logger.info(
                "Detector '%s': bundle has %d profiles; preserving their names",
                name,
                len(profiles),
            )
        return [
            DetectorSpec(
                profile=profile,
                device_class=device_class,
                source_kind="profile",
                source_value=path.name,
            )
            for profile in profiles
        ]

    if entry.get("learn"):
        recording_ref = str(entry["learn"]).strip()
        wav = _resolve(recording_ref, sounds_dir(), data_dir())
        if wav is None:
            logger.error("Detector '%s': recording '%s' was not found", name or recording_ref, recording_ref)
            return []
        try:
            profile = learn_profile_from_file(wav, name=name or None)
        except Exception as exc:
            logger.error("Detector '%s': could not learn from %s (%s)", name or wav, wav, exc)
            return []
        try:
            profiles_dir().mkdir(parents=True, exist_ok=True)
            output = profiles_dir() / f"{wav.stem}.yaml"
            save_profile_to_yaml(profile, output)
            logger.info("Learned profile from %s -> %s", wav.name, output)
        except OSError as exc:
            logger.warning("Learned profile but could not save it: %s", exc)
        return [
            DetectorSpec(
                profile=profile,
                device_class=_device_class_for(entry, _DEFAULT_DEVICE_CLASS),
                source_kind="learn",
                source_value=wav.name,
            )
        ]

    logger.error(
        "Detector '%s' has no source; use preset, profile, or learn",
        name or "(unnamed)",
    )
    return []


def _dedupe_names(specs: List[DetectorSpec]) -> List[DetectorSpec]:
    seen: dict[str, int] = {}
    for spec in specs:
        base = spec.profile.name
        if base not in seen:
            seen[base] = 1
            continue
        seen[base] += 1
        replacement = f"{base} {seen[base]}"
        logger.warning("Duplicate detector '%s'; renamed to '%s'", base, replacement)
        spec.profile.name = replacement
    return specs


def _normalize_device_index(value: object) -> int | None:
    if value in (None, "", -1, "-1"):
        return None
    return int(value)


def load_app_config(options: dict[str, object] | None = None) -> AppConfig:
    """Build and validate one complete runtime generation."""

    raw_options = dict(read_options() if options is None else options)
    entries = raw_options.get("detectors") or _DEFAULT_DETECTORS

    specs: List[DetectorSpec] = []
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict):
                specs.extend(_profiles_from_entry(entry))
            else:
                logger.error("Ignoring malformed detector entry: %r", entry)
    else:
        logger.error("The detectors option must be a list")

    specs = _dedupe_names(specs)
    audio = AudioSettings(
        sample_rate=int(raw_options.get("sample_rate", 44100) or 44100),
        device_index=_normalize_device_index(raw_options.get("device_index")),
        channels=1,
    )
    return AppConfig(
        detectors=specs,
        audio=audio,
        hold_seconds=float(raw_options.get("hold_seconds", 30) or 30),
        debug=bool(raw_options.get("debug", False)),
        options=raw_options,
    )
