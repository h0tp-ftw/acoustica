"""Configuration utilities for the acoustic alarm engine.

This module centralizes all configuration logic for resolution settings,
presets, and engine defaults. It provides helper functions for computing
optimal settings based on loaded profiles and supports loading a unified
global configuration file.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Union

import yaml

from .models import AlarmProfile, ResolutionConfig
from .profiles import _parse_profile, load_profiles_from_yaml

logger = logging.getLogger(__name__)

# Default resolution values
DEFAULT_MIN_TONE_DURATION = 0.04  # seconds (requires ~2 chunks to confirm)
DEFAULT_DROPOUT_TOLERANCE = 0.03  # seconds (tolerates 1 missing chunk)
DEFAULT_MIN_MAGNITUDE = 10.0  # Threshold for peak detection

# High-resolution preset values
HIGHRES_MIN_TONE_DURATION = 0.05  # 50ms
HIGHRES_DROPOUT_TOLERANCE = 0.05  # 50ms


def compute_finest_resolution(profiles: List[AlarmProfile]) -> Tuple[float, float]:
    """Compute the finest resolution needed across all profiles.

    Examines all profiles and returns the smallest min_tone_duration
    and dropout_tolerance values. This allows a single EventGenerator
    to capture events at the resolution needed by all profiles.

    Args:
        profiles: List of AlarmProfile objects to analyze.

    Returns:
        A tuple containing (min_tone_duration, dropout_tolerance) as floats.
    """
    finest_min_tone = DEFAULT_MIN_TONE_DURATION
    finest_dropout = DEFAULT_DROPOUT_TOLERANCE

    for profile in profiles:
        if profile.resolution:
            finest_min_tone = min(finest_min_tone, profile.resolution.min_tone_duration)
            finest_dropout = min(finest_dropout, profile.resolution.dropout_tolerance)

    return finest_min_tone, finest_dropout


def get_resolution_for_profile(profile: AlarmProfile) -> ResolutionConfig:
    """Get the effective resolution config for a profile.

    Returns the profile's resolution if set, otherwise returns defaults.

    Args:
        profile: The AlarmProfile to get resolution for.

    Returns:
        ResolutionConfig object with the effective settings.
    """
    if profile.resolution:
        return profile.resolution
    return ResolutionConfig.standard()


@dataclass
class SystemConfig:
    """System-level configuration settings.

    Attributes:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Optional path to a log file.
    """

    log_level: str = "INFO"
    log_file: Optional[str] = None


@dataclass
class AudioSettings:
    """Audio capture configuration settings.

    Attributes:
        sample_rate: Audio sampling rate in Hz.
        chunk_size: Number of samples per buffer.
        device_index: Specific audio device index (None for default).
        channels: Number of audio channels (usually 1 for mono).
    """

    sample_rate: int = 44100
    chunk_size: int = 1024  # High-res default
    device_index: Optional[int] = None
    channels: int = 1


@dataclass
class EngineConfig:
    """Complete configuration for the Engine's detection pipeline.

    This consolidates all engine settings in one place for easier management.

    Attributes:
        sample_rate: Audio sample rate in Hz.
        chunk_size: FFT chunk size in samples.
        min_tone_duration: Minimum tone duration to register (computed from profiles).
        dropout_tolerance: Max gap before tone considered ended (computed from profiles).
        min_magnitude: Threshold for peak detection.

        # --- Advanced DSP Settings ---
        min_sharpness: Minimum prominence of a spectral peak (default 1.5).
        noise_floor_factor: Multiplier for adaptive noise floor (default 3.0).
        max_peaks: Maximum peaks to track per chunk (default 5).

        # --- Advanced Generation Settings ---
        frequency_tolerance: Hz range to consider peaks as the same tone (default 50.0).
        freq_smoothing: Alpha for EMA frequency tracking (default 0.3).
        dip_threshold: Ratio for instantaneous dip detection (default 0.6).
        strong_signal_ratio: Ratio to consider signal "strong" for duration (default 0.5).
        coalesce_ratio: Overlap ratio for merging concurrent events (default 0.5).

        # --- Advanced Matching Settings ---
        max_buffer_duration: Seconds of history to keep in memory (default 60.0).
        noise_skip_limit: Max number of noise events to skip during matching (default 2).
        duration_relax_low: Multiplier for minimum segment duration (default 0.8).
        duration_relax_high: Multiplier for maximum segment duration (default 1.5).
    """

    sample_rate: int = 44100
    chunk_size: int = 1024
    min_tone_duration: float = DEFAULT_MIN_TONE_DURATION
    dropout_tolerance: float = DEFAULT_DROPOUT_TOLERANCE
    min_magnitude: float = DEFAULT_MIN_MAGNITUDE  # Threshold for peak detection

    # Advanced DSP
    min_sharpness: float = 1.5
    noise_floor_factor: float = 3.0
    noise_learning_rate: float = 0.01  # Alpha for background noise profile updates
    max_peaks: int = 5

    # Advanced Generation
    frequency_tolerance: float = 50.0
    freq_smoothing: float = 0.3
    dip_threshold: float = 0.6
    strong_signal_ratio: float = 0.5
    coalesce_ratio: float = 0.5

    # Advanced Matching
    max_buffer_duration: float = 60.0
    noise_skip_limit: int = 2
    duration_relax_low: float = 0.8
    duration_relax_high: float = 1.5

    @classmethod
    def from_profiles(
        cls,
        profiles: List[AlarmProfile],
        sample_rate: int = 44100,
        chunk_size: int = 4096,
    ) -> "EngineConfig":
        """Create an EngineConfig with resolution computed from profiles.

        This is the recommended way to create an EngineConfig - it automatically
        sets the resolution to the finest values needed by any profile.

        Args:
            profiles: List of AlarmProfile objects.
            sample_rate: Audio sample rate (default 44100).
            chunk_size: FFT chunk size (default 4096, will be reduced to 2048 for high-res).

        Returns:
            EngineConfig with computed resolution settings.
        """
        min_tone, dropout = compute_finest_resolution(profiles)

        # If any profile needs high-res, reduce chunk size for better temporal resolution
        if min_tone < DEFAULT_MIN_TONE_DURATION or dropout < DEFAULT_DROPOUT_TOLERANCE:
            chunk_size = min(chunk_size, 2048)  # Cap at 2048 for high-res

        return cls(
            sample_rate=sample_rate,
            chunk_size=chunk_size,
            min_tone_duration=min_tone,
            dropout_tolerance=dropout,
        )

    @classmethod
    def from_single_profile(
        cls,
        profile: AlarmProfile,
        sample_rate: int = 44100,
        chunk_size: int = 1024,
    ) -> "EngineConfig":
        """Create an EngineConfig tailored for a SINGLE profile.

        Used in parallel pipeline architectures where each profile gets its own engine.

        Args:
            profile: The single AlarmProfile object.
            sample_rate: Audio sample rate.
            chunk_size: FFT chunk size.

        Returns:
            EngineConfig with resolution settings matching the profile.
        """
        # Default requirements
        min_tone = DEFAULT_MIN_TONE_DURATION
        dropout = DEFAULT_DROPOUT_TOLERANCE

        # Override if profile has specific requirements
        if profile.resolution:
            min_tone = profile.resolution.min_tone_duration
            dropout = profile.resolution.dropout_tolerance

        # Adaptive chunk size for high resolution
        target_min_mag = DEFAULT_MIN_MAGNITUDE

        if min_tone < 0.05 or dropout < 0.05:
            # For very fast patterns, ensure chunk size isn't too large
            # 1024 samples @ 44.1kHz is ~23ms, which is fine for 50ms events.
            chunk_size = min(chunk_size, 1024)

        # Scale min_magnitude based on chunk size reduction relative to standard (4096)
        # FFT magnitude is proportional to N. If we use smaller N, we need smaller threshold.
        # Reference: N=4096, Threshold=DEFAULT_MIN_MAGNITUDE
        if chunk_size < 4096:
            scale_factor = chunk_size / 4096.0
            target_min_mag = DEFAULT_MIN_MAGNITUDE * scale_factor
            # Avoid going too low (noise floor)
            target_min_mag = max(target_min_mag, 1.0)

            # Also scale frequency_tolerance UP
            # Smaller N = wider bins = more jitter.
            # 4096 -> ~10Hz bins. 1024 -> ~43Hz bins.
            # Scale tolerance inversely to chunks size (approx)
            bin_ratio = 4096.0 / chunk_size
            # Base tolerance 50.0 (covering ~5 bins at 4096).
            # For 1024, we need ~150-200.
            # Let's scale by sqrt(bin_ratio) or linear?
            # Linear bin width growth -> Linear tolerance growth?
            # 50 * 4 = 200Hz. This might be too wide, but needed if jitter is >86Hz.
            # Let's try scaling max.
            target_freq_tol = 50.0 * (4096.0 / chunk_size)  # Full linear scaling = 200Hz

        else:
            target_freq_tol = 50.0

        return cls(
            sample_rate=sample_rate,
            chunk_size=chunk_size,
            min_tone_duration=min_tone,
            dropout_tolerance=dropout,
            min_magnitude=target_min_mag,
            frequency_tolerance=target_freq_tol,
        )

    @classmethod
    def high_resolution(cls, sample_rate: int = 44100) -> "EngineConfig":
        """High-resolution preset for fast patterns with small gaps.

        Use this for patterns with <100ms gaps between tones.

        Args:
            sample_rate: Audio sample rate (default 44100).

        Returns:
            EngineConfig with high-res settings.
        """
        return cls(
            sample_rate=sample_rate,
            chunk_size=1024,
            min_tone_duration=HIGHRES_MIN_TONE_DURATION,
            dropout_tolerance=HIGHRES_DROPOUT_TOLERANCE,
        )

    @classmethod
    def standard(cls, sample_rate: int = 44100) -> "EngineConfig":
        """Standard preset for noisy environments.

        Use this for typical alarm detection where noise resilience is important.

        Args:
            sample_rate: Audio sample rate (default 44100).

        Returns:
            EngineConfig with standard settings.
        """
        return cls(
            sample_rate=sample_rate,
            chunk_size=1024,
            min_tone_duration=DEFAULT_MIN_TONE_DURATION,
            dropout_tolerance=DEFAULT_DROPOUT_TOLERANCE,
        )


@dataclass
class GlobalConfig:
    """Unified configuration for the entire application.

    This class serves as the single source of truth for configuration,
    loading system settings, audio parameters, and alarm profiles from
    a single YAML file or structure.
    """

    system: SystemConfig = field(default_factory=SystemConfig)
    audio: AudioSettings = field(default_factory=AudioSettings)
    profiles: List[AlarmProfile] = field(default_factory=list)
    # The calculated engine config based on the above
    engine: EngineConfig = field(default_factory=EngineConfig)

    @classmethod
    def load(cls, path: Union[str, Path]) -> "GlobalConfig":
        """Load the global configuration from a YAML file.

        The YAML file should have the following structure:
        ```yaml
        system:
          log_level: INFO
        audio:
          sample_rate: 44100
        profiles:
          - name: "Smoke Alarm"
            segments: ...
          - include: "path/to/other/profiles.yaml"
        ```

        Args:
            path: Path to the main configuration YAML file.

        Returns:
            A GlobalConfig object populated with the settings.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}

        # 1. Parse System Config
        sys_data = data.get("system", {})
        system_config = SystemConfig(
            log_level=sys_data.get("log_level", "INFO"),
            log_file=sys_data.get("log_file"),
        )

        # 2. Parse Audio Settings
        audio_data = data.get("audio", {})
        audio_config = AudioSettings(
            sample_rate=audio_data.get("sample_rate", 44100),
            chunk_size=audio_data.get("chunk_size", 4096),
            device_index=audio_data.get("device_index"),
            channels=audio_data.get("channels", 1),
        )

        # 3. Parse Profiles
        profiles: List[AlarmProfile] = []
        raw_profiles = data.get("profiles", [])

        # Support just a list or a dict-based inclusion
        if isinstance(raw_profiles, list):
            for item in raw_profiles:
                if "include" in item:
                    # Include external file(s)
                    include_path = item["include"]
                    # Handle relative paths relative to the config file
                    if not os.path.isabs(include_path):
                        include_path = path.parent / include_path

                    # Use glob expansion if * is present
                    if "*" in str(include_path):
                        # Logic for glob expansion could be added here
                        # For now, simplistic exact path loading
                        pass

                    # If it's a file, load it
                    p_path = Path(include_path)
                    if p_path.is_file():
                        loaded = load_profiles_from_yaml(p_path)
                        profiles.extend(loaded)
                    elif p_path.is_dir():
                        # Determine handling for directories if needed
                        pass
                    else:
                        logger.warning(f"Included profile path not found: {include_path}")
                elif "name" in item:
                    # Inline profile definition
                    profiles.append(_parse_profile(item))

        # 4. Generate Engine Config
        # We use the profiles to determine the best resolution
        engine_config = EngineConfig.from_profiles(
            profiles,
            sample_rate=audio_config.sample_rate,
            chunk_size=audio_config.chunk_size,
        )

        # 5. Apply Engine Overrides from YAML
        # Allow explicit configuration to override profile-based defaults
        engine_data = data.get("engine", {})
        if engine_data:
            if "chunk_size" in engine_data:
                engine_config.chunk_size = int(engine_data["chunk_size"])
            if "min_tone_duration" in engine_data:
                engine_config.min_tone_duration = float(engine_data["min_tone_duration"])
            if "dropout_tolerance" in engine_data:
                engine_config.dropout_tolerance = float(engine_data["dropout_tolerance"])
            if "min_magnitude" in engine_data:
                engine_config.min_magnitude = float(engine_data["min_magnitude"])

            # Advanced DSP
            if "min_sharpness" in engine_data:
                engine_config.min_sharpness = float(engine_data["min_sharpness"])
            if "noise_floor_factor" in engine_data:
                engine_config.noise_floor_factor = float(engine_data["noise_floor_factor"])
            if "max_peaks" in engine_data:
                engine_config.max_peaks = int(engine_data["max_peaks"])
            if "noise_learning_rate" in engine_data:
                engine_config.noise_learning_rate = float(engine_data["noise_learning_rate"])

            # Advanced Generation
            if "frequency_tolerance" in engine_data:
                engine_config.frequency_tolerance = float(engine_data["frequency_tolerance"])
            if "freq_smoothing" in engine_data:
                engine_config.freq_smoothing = float(engine_data["freq_smoothing"])
            if "dip_threshold" in engine_data:
                engine_config.dip_threshold = float(engine_data["dip_threshold"])
            if "strong_signal_ratio" in engine_data:
                engine_config.strong_signal_ratio = float(engine_data["strong_signal_ratio"])
            if "coalesce_ratio" in engine_data:
                engine_config.coalesce_ratio = float(engine_data["coalesce_ratio"])

            # Advanced Matching
            if "max_buffer_duration" in engine_data:
                engine_config.max_buffer_duration = float(engine_data["max_buffer_duration"])
            if "noise_skip_limit" in engine_data:
                engine_config.noise_skip_limit = int(engine_data["noise_skip_limit"])
            if "duration_relax_low" in engine_data:
                engine_config.duration_relax_low = float(engine_data["duration_relax_low"])
            if "duration_relax_high" in engine_data:
                engine_config.duration_relax_high = float(engine_data["duration_relax_high"])

        return cls(
            system=system_config,
            audio=audio_config,
            profiles=profiles,
            engine=engine_config,
        )
