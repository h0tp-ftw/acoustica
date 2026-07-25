"""Simplified YAML configuration loader using external library."""

import logging
from typing import List, Union
from pathlib import Path

# Import from the external library
from acoustic_engine.models import AlarmProfile
from acoustic_engine.profiles import (
    load_profile_from_yaml as lib_load_profile,
    load_profiles_from_yaml as lib_load_profiles,
    save_profile_to_yaml as lib_save_profile,
)

logger = logging.getLogger(__name__)

def load_profile_from_yaml(path: Union[str, Path]) -> AlarmProfile:
    """Load a single AlarmProfile from a YAML file."""
    return lib_load_profile(path)

def load_profiles_from_yaml(path: Union[str, Path]) -> List[AlarmProfile]:
    """Load multiple AlarmProfiles from a YAML file."""
    return lib_load_profiles(path)

def save_profile_to_yaml(profile: AlarmProfile, path: Union[str, Path]) -> None:
    """Save an AlarmProfile to a YAML file."""
    lib_save_profile(profile, path)
