"""YAML configuration loader for AlarmProfiles.

This module provides functionality to load and save `AlarmProfile` objects
from YAML files. It supports various YAML structures including single profiles,
lists of profiles, and bundled profiles. It handles the parsing of segments,
frequency ranges, and resolution settings.
"""

import logging
from pathlib import Path
from typing import List, Union

import yaml

from .models import AlarmProfile, Range, ResolutionConfig, Segment

logger = logging.getLogger(__name__)


def load_profile_from_yaml(path: Union[str, Path]) -> AlarmProfile:
    """Load a single AlarmProfile from a YAML file.

    This function expects the YAML file to describe exactly one profile.

    Example YAML format:
    ```yaml
    name: "SmokeAlarm"
    confirmation_cycles: 2
    segments:
      - type: "tone"
        frequency:
          min: 2900
          max: 3100
        duration:
          min: 0.4
          max: 0.6
      - type: "silence"
        duration:
          min: 0.1
          max: 0.3
    ```

    Args:
        path: Path to the YAML file.

    Returns:
        The valid AlarmProfile object parsed from the file.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the YAML structure is invalid.
    """
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    return _parse_profile(data)


def load_profiles_from_yaml(path: Union[str, Path]) -> List[AlarmProfile]:
    """Load multiple AlarmProfiles from a YAML file.

    This function is flexible and supports three different top-level structures
    in the YAML file:
    1. A single profile dictionary (returns a list with one element).
    2. A list of profile dictionaries.
    3. A "bundled" dictionary with a 'profiles' key containing a list.

    Args:
        path: Path to the YAML file.

    Returns:
        A list of loaded AlarmProfile objects.
    """
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    # Format 3: Bundled profiles
    if isinstance(data, dict) and "profiles" in data:
        return [_parse_profile(p) for p in data["profiles"]]

    # Format 2: List of profiles
    if isinstance(data, list):
        return [_parse_profile(p) for p in data]

    # Format 1: Single profile (fallback)
    return [_parse_profile(data)]


def _parse_profile(data: dict) -> AlarmProfile:
    """Parse a raw dictionary into an AlarmProfile object.

    Handles defaults, type conversion, and structure validation for
    segments, frequency ranges, and resolution settings.

    Args:
        data: Use dictionary containing profile definition.

    Returns:
        A validated AlarmProfile object.
    """
    segments = []

    for seg_data in data.get("segments", []):
        seg_type = seg_data.get("type", "tone")

        # Parse frequency range (only for tones)
        frequency = None
        if seg_type == "tone" and "frequency" in seg_data:
            freq_data = seg_data["frequency"]
            if isinstance(freq_data, dict):
                frequency = Range(
                    min=float(freq_data.get("min", 0)),
                    max=float(freq_data.get("max", 20000)),
                )
            else:
                # Single value: apply ±5% tolerance
                freq = float(freq_data)
                frequency = Range(min=freq * 0.95, max=freq * 1.05)

        # Parse duration range
        dur_data = seg_data.get("duration", {"min": 0.1, "max": 1.0})
        if isinstance(dur_data, dict):
            duration = Range(
                min=float(dur_data.get("min", 0.1)), max=float(dur_data.get("max", 1.0))
            )
        else:
            # Single value: apply ±20% tolerance
            dur = float(dur_data)
            duration = Range(min=dur * 0.8, max=dur * 1.2)

        segments.append(
            Segment(
                type=seg_type,
                frequency=frequency,
                duration=duration,
                min_magnitude=float(seg_data.get("min_magnitude", 0.05)),
            )
        )

    # Parse resolution settings if present
    resolution = None
    if "resolution" in data:
        res_data = data["resolution"]
        resolution = ResolutionConfig(
            min_tone_duration=float(res_data.get("min_tone_duration", 0.1)),
            dropout_tolerance=float(res_data.get("dropout_tolerance", 0.15)),
        )

    return AlarmProfile(
        name=data.get("name", "UnnamedProfile"),
        segments=segments,
        confirmation_cycles=int(data.get("confirmation_cycles", 1)),
        reset_timeout=float(data.get("reset_timeout", 10.0)),
        window_duration=data.get("window_duration"),
        eval_frequency=float(data.get("eval_frequency", 0.5)),
        resolution=resolution,
    )


def save_profile_to_yaml(profile: AlarmProfile, path: Union[str, Path]) -> None:
    """Save an AlarmProfile to a YAML file.

    Serializes the profile object back to a YAML representation.

    Args:
        profile: The AlarmProfile object to save.
        path: Destination file path.
    """
    data = {
        "name": profile.name,
        "confirmation_cycles": profile.confirmation_cycles,
        "reset_timeout": profile.reset_timeout,
        "segments": [],
    }

    for seg in profile.segments:
        seg_data = {
            "type": seg.type,
            "duration": {"min": seg.duration.min, "max": seg.duration.max},
        }

        if seg.type == "tone" and seg.frequency:
            seg_data["frequency"] = {"min": seg.frequency.min, "max": seg.frequency.max}
            seg_data["min_magnitude"] = seg.min_magnitude

        data["segments"].append(seg_data)

    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Saved profile '{profile.name}' to {path}")


def save_profiles_to_yaml(profiles: List[AlarmProfile], path: Union[str, Path]) -> None:
    """Save multiple AlarmProfiles to a YAML file (as a 'profiles' list)."""
    data_list = []

    for profile in profiles:
        p_data = {
            "name": profile.name,
            "confirmation_cycles": profile.confirmation_cycles,
            "reset_timeout": profile.reset_timeout,
            "segments": [],
        }

        for seg in profile.segments:
            seg_data = {
                "type": seg.type,
                "duration": {"min": seg.duration.min, "max": seg.duration.max},
            }

            if seg.type == "tone" and seg.frequency:
                seg_data["frequency"] = {"min": seg.frequency.min, "max": seg.frequency.max}
                # seg_data["min_magnitude"] = seg.min_magnitude # Optional

            p_data["segments"].append(seg_data)
        data_list.append(p_data)

    # Save as list of profiles
    with open(path, "w") as f:
        yaml.dump(data_list, f, default_flow_style=False, sort_keys=False)
