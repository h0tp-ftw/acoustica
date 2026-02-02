"""Acoustic Alarm Engine - Real-time audio pattern detection.

A standalone library for detecting acoustic alarm patterns including
smoke alarms, CO detectors, appliance beeps, and other repetitive sounds.

Usage:
    from acoustic_engine import Engine, AudioConfig
    from acoustic_engine.profiles import load_profiles_from_yaml

    profiles = load_profiles_from_yaml("smoke_alarm.yaml")
    engine = Engine(profiles, AudioConfig(), on_detection=print)
    engine.start()
"""

__version__ = "1.0.0"
__author__ = "Your Name"

# Core exports
from .analysis.event_buffer import EventBuffer
from .analysis.windowed_matcher import WindowedMatcher
from .config import EngineConfig, compute_finest_resolution
from .engine import Engine
from .input.listener import AudioConfig, AudioListener
from .models import AlarmProfile, Range, ResolutionConfig, Segment
from .processing.filter import FrequencyFilter
from .profiles import (
    load_profile_from_yaml,
    load_profiles_from_yaml,
    save_profile_to_yaml,
)

__all__ = [
    # Version
    "__version__",
    # Core classes
    "Engine",
    "AudioConfig",
    "AudioListener",
    "FrequencyFilter",
    "EventBuffer",
    "WindowedMatcher",
    # Configuration
    "EngineConfig",
    "ResolutionConfig",
    "compute_finest_resolution",
    # Models
    "AlarmProfile",
    "Segment",
    "Range",
    # Profile loading
    "load_profile_from_yaml",
    "load_profiles_from_yaml",
    "save_profile_to_yaml",
]
