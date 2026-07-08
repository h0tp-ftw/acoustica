"""Build the detector runtime config from Home Assistant add-on options.

Reads ``/data/options.json`` (the schema is declared in ``config.yaml``) and
turns each ``detectors`` entry into an :class:`acoustic_engine.models.AlarmProfile`
using one of three sources:

- ``preset``  — a built-in profile shipped with the engine (``smoke_t3``/``co_t4``)
- ``profile`` — a profile/bundle YAML the user dropped under ``/config``
- ``learn``   — a recording (WAV) the engine turns into a profile on first run

Everything heavy (DSP, matching, the learn algorithm) lives in the engine; this
module only locates files and maps the add-on's options onto the engine's API.
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from acoustic_engine.config import AudioSettings
from acoustic_engine.learn import learn_profile_from_file
from acoustic_engine.models import AlarmProfile
from acoustic_engine.presets import list_presets, load_preset
from acoustic_engine.profiles import load_profiles_from_yaml, save_profile_to_yaml

logger = logging.getLogger(__name__)

# Where add-on options land, and where we keep user assets + the discovery file.
# Resolved at call time (not import) and overridable via env, so the whole thing
# runs — and tests — off-HAOS too.
def _options_path() -> Path:
    return Path(os.getenv("OPTIONS_JSON", "/data/options.json"))


def _data_dir() -> Path:
    return Path(os.getenv("ACOUSTIC_DATA_DIR", "/config/acoustica"))


def _sounds_dir() -> Path:
    return _data_dir() / "sounds"


def _learned_dir() -> Path:
    return _data_dir() / "profiles"

# Sensible binary_sensor device_class for each built-in preset.
_PRESET_DEVICE_CLASS = {"smoke_t3": "smoke", "co_t4": "carbon_monoxide"}
_DEFAULT_DEVICE_CLASS = "sound"

# Used when no options file exists at all (fresh install / local dev): detect the
# two standardized life-safety alarms out of the box.
_DEFAULT_DETECTORS = [
    {"name": "Smoke Alarm", "preset": "smoke_t3", "device_class": "smoke"},
    {"name": "CO Alarm", "preset": "co_t4", "device_class": "carbon_monoxide"},
]


@dataclass
class DetectorSpec:
    """One configured detector: a pattern plus the entity's device_class."""

    profile: AlarmProfile
    device_class: str


@dataclass
class AppConfig:
    """Everything ``main`` needs to start the engine and the HA bridge."""

    detectors: List[DetectorSpec]
    audio: AudioSettings
    hold_seconds: float
    debug: bool

    @property
    def profiles(self) -> List[AlarmProfile]:
        return [d.profile for d in self.detectors]

    @property
    def device_classes(self) -> dict:
        """Map profile name -> device_class, as the bridge/integration key on."""
        return {d.profile.name: d.device_class for d in self.detectors}


def _read_options() -> dict:
    """Load options.json, or return {} (so defaults apply) if it's absent/bad."""
    path = _options_path()
    if not path.exists():
        logger.warning("No options at %s; using built-in defaults.", path)
        return {}
    try:
        return json.loads(path.read_text()) or {}
    except (OSError, ValueError) as e:
        logger.error("Could not read %s (%s); using built-in defaults.", path, e)
        return {}


def _resolve(name: str, *search_dirs: Path) -> Optional[Path]:
    """Find ``name`` as an absolute path or relative to any of ``search_dirs``."""
    candidate = Path(name)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    for base in search_dirs:
        p = base / name
        if p.exists():
            return p
    return None


def _device_class_for(entry: dict, default: str) -> str:
    dc = entry.get("device_class")
    return dc if dc else default


def _profiles_from_entry(entry: dict) -> List[DetectorSpec]:
    """Turn one ``detectors`` option entry into one or more DetectorSpecs.

    A ``profile`` YAML may be a bundle of several profiles; each becomes its own
    sensor. ``preset``/``learn`` always yield exactly one.
    """
    name = (entry.get("name") or "").strip()

    if entry.get("preset"):
        preset = entry["preset"].strip()
        try:
            profile = load_preset(preset)
        except KeyError:
            logger.error(
                "Detector '%s': unknown preset '%s'. Available: %s. Skipping.",
                name or preset, preset, ", ".join(list_presets()),
            )
            return []
        if name:
            profile.name = name
        return [DetectorSpec(profile, _device_class_for(entry, _PRESET_DEVICE_CLASS.get(preset, _DEFAULT_DEVICE_CLASS)))]

    if entry.get("profile"):
        data_dir = _data_dir()
        path = _resolve(entry["profile"].strip(), _learned_dir(), data_dir, Path("/config"))
        if not path:
            logger.error(
                "Detector '%s': profile file '%s' not found under %s. Skipping.",
                name or entry["profile"], entry["profile"], data_dir,
            )
            return []
        try:
            profiles = load_profiles_from_yaml(path)
        except Exception as e:  # ProfileError, parse errors, etc.
            logger.error("Detector '%s': could not load %s (%s). Skipping.", name or path, path, e)
            return []
        dc = _device_class_for(entry, _DEFAULT_DEVICE_CLASS)
        if len(profiles) == 1 and name:
            profiles[0].name = name
        elif len(profiles) > 1 and name:
            logger.info("Detector '%s': bundle has %d profiles; keeping their own names.", name, len(profiles))
        return [DetectorSpec(p, dc) for p in profiles]

    if entry.get("learn"):
        sounds_dir = _sounds_dir()
        wav = _resolve(entry["learn"].strip(), sounds_dir, _data_dir(), Path("/config"))
        if not wav:
            logger.error(
                "Detector '%s': recording '%s' not found under %s. Skipping.",
                name or entry["learn"], entry["learn"], sounds_dir,
            )
            return []
        try:
            profile = learn_profile_from_file(wav, name=name or None)
        except Exception as e:
            logger.error("Detector '%s': could not learn from %s (%s). Skipping.", name or wav, wav, e)
            return []
        # Persist the learned profile so the user can inspect/tweak it.
        try:
            learned_dir = _learned_dir()
            learned_dir.mkdir(parents=True, exist_ok=True)
            out = learned_dir / f"{wav.stem}.yaml"
            save_profile_to_yaml(profile, out)
            logger.info("Learned profile from %s -> %s", wav.name, out)
        except OSError as e:
            logger.warning("Learned profile but could not save it: %s", e)
        return [DetectorSpec(profile, _device_class_for(entry, _DEFAULT_DEVICE_CLASS))]

    logger.error(
        "Detector '%s' has no source. Give it one of: preset, profile, or learn. Skipping.",
        name or "(unnamed)",
    )
    return []


def _dedupe_names(specs: List[DetectorSpec]) -> List[DetectorSpec]:
    """Ensure profile names are unique (they key the HA entity + bridge state)."""
    seen: dict = {}
    for spec in specs:
        base = spec.profile.name
        if base not in seen:
            seen[base] = 1
            continue
        seen[base] += 1
        new = f"{base} {seen[base]}"
        logger.warning("Duplicate detector name '%s'; renaming one to '%s'.", base, new)
        spec.profile.name = new
    return specs


def load_app_config() -> AppConfig:
    """Read add-on options and build the full runtime configuration."""
    opts = _read_options()

    entries = opts.get("detectors")
    if not entries:
        entries = _DEFAULT_DETECTORS

    specs: List[DetectorSpec] = []
    for entry in entries:
        if isinstance(entry, dict):
            specs.extend(_profiles_from_entry(entry))
        else:
            logger.error("Ignoring malformed detector entry: %r", entry)
    specs = _dedupe_names(specs)

    device_index = opts.get("device_index")
    if isinstance(device_index, str):
        device_index = int(device_index) if device_index.strip() else None

    audio = AudioSettings(
        sample_rate=int(opts.get("sample_rate", 44100) or 44100),
        device_index=device_index,
        channels=1,
    )

    return AppConfig(
        detectors=specs,
        audio=audio,
        hold_seconds=float(opts.get("hold_seconds", 30) or 30),
        debug=bool(opts.get("debug", False)),
    )
