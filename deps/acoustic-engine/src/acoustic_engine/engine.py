"""Main Engine class - orchestrates the detection pipeline.

This module contains the core `Engine` class which ties together all components
of the acoustic alarm detection system: audio capture, signal processing,
event generation, and pattern matching.
"""

import logging
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional, Union

import numpy as np

from .analysis.generator import EventGenerator
from .analysis.windowed_matcher import WindowedMatcher
from .config import (
    AudioSettings,
    EngineConfig,
    GlobalConfig,
)
from .events import PatternMatchEvent
from .input.listener import AudioListener
from .models import AlarmProfile
from .processing.dsp import SpectralMonitor
from .processing.filter import FrequencyFilter

logger = logging.getLogger(__name__)


class Engine:
    """Acoustic Alarm Detection Engine.

    Orchestrates the full detection pipeline:
    Audio Input → DSP/FFT → Frequency Filter → Event Generation → Pattern Matching → Callbacks

    The engine can be configured manually or loaded from a configuration file.

    Example:
        >>> from acoustic_engine import Engine
        >>> engine = Engine.from_yaml("config.yaml")
        >>> engine.start()  # Blocking
    """

    def __init__(
        self,
        profiles: List[AlarmProfile],
        audio_config: Optional[AudioSettings] = None,
        engine_config: Optional[EngineConfig] = None,
        on_detection: Optional[Callable[[str], None]] = None,
        on_match: Optional[Callable[[PatternMatchEvent], None]] = None,
    ):
        """Initialize the detection engine.

        Args:
            profiles: List of AlarmProfile patterns to detect.
            audio_config: Audio capture settings (uses defaults if None).
            engine_config: Engine pipeline settings (uses defaults/computed if None).
            on_detection: Simple callback invoked with just the profile name (str)
                          when an alarm is confirmed.
            on_match: Detailed callback invoked with the full PatternMatchEvent object
                      when an alarm is confirmed.
        """
        self.profiles = profiles
        self.audio_config = audio_config or AudioSettings()
        self.on_detection = on_detection
        self.on_match = on_match

        # Use provided engine config or compute optimal settings from profiles
        if engine_config:
            self.engine_config = engine_config
        else:
            self.engine_config = EngineConfig.from_profiles(
                profiles,
                sample_rate=self.audio_config.sample_rate,
                chunk_size=self.audio_config.chunk_size,
            )

        # State management
        self._alarm_active = False
        self._current_time = 0.0
        self._running = False

        # Pipeline components initialization
        self._dsp = SpectralMonitor(
            self.engine_config.sample_rate,
            self.engine_config.chunk_size,
            min_magnitude=self.engine_config.min_magnitude,
            min_sharpness=self.engine_config.min_sharpness,
            noise_floor_factor=self.engine_config.noise_floor_factor,
            max_peaks=self.engine_config.max_peaks,
            noise_learning_rate=self.engine_config.noise_learning_rate,
        )
        self._freq_filter = FrequencyFilter(self.profiles)
        self._generator = EventGenerator(
            self.engine_config.sample_rate,
            self.engine_config.chunk_size,
            min_tone_duration=self.engine_config.min_tone_duration,
            dropout_tolerance=self.engine_config.dropout_tolerance,
            frequency_tolerance=self.engine_config.frequency_tolerance,
            freq_smoothing=self.engine_config.freq_smoothing,
            dip_threshold=self.engine_config.dip_threshold,
            strong_signal_ratio=self.engine_config.strong_signal_ratio,
            coalesce_ratio=self.engine_config.coalesce_ratio,
        )
        self._matcher = WindowedMatcher(
            self.profiles,
            max_buffer_duration=self.engine_config.max_buffer_duration,
            noise_skip_limit=self.engine_config.noise_skip_limit,
            duration_relax_low=self.engine_config.duration_relax_low,
            duration_relax_high=self.engine_config.duration_relax_high,
        )

        # Audio listener (created on start)
        self._listener: Optional[AudioListener] = None

        logger.info(
            f"Engine initialized with {len(profiles)} profile(s): {[p.name for p in profiles]}"
        )
        logger.debug(f"Engine Config: {self.engine_config}")

    @classmethod
    def from_config(cls, config: GlobalConfig) -> "Engine":
        """Create an Engine instance from a GlobalConfig object.

        Args:
            config: The GlobalConfig object containing all settings.

        Returns:
            Configured Engine instance.
        """
        # Configure logging from system config if needed
        # (Usually logging is configured at app startup, but we can respect log level here)
        logging.getLogger().setLevel(config.system.log_level)

        return cls(
            profiles=config.profiles,
            audio_config=config.audio,
            engine_config=config.engine,
        )

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "Engine":
        """Create an Engine instance directly from a YAML configuration file.

        Args:
            path: Path to the YAML configuration file.

        Returns:
            Configured Engine instance.
        """
        config = GlobalConfig.load(path)
        return cls.from_config(config)

    def process_chunk(self, audio_chunk: np.ndarray) -> bool:
        """Process a single audio chunk through the pipeline.

        This method drives the entire detection logic for one block of audio.
        It can be called directly if you are manually handling audio capture
        instead of using the built-in listener.

        Args:
            audio_chunk: Raw audio samples (int16, mono).

        Returns:
            True if an alarm was detected and triggered in this specific chunk.
        """
        # Time keeping based on configured chunk size (which dictates temporal resolution)
        chunk_duration = self.engine_config.chunk_size / self.engine_config.sample_rate
        self._current_time += chunk_duration

        # 1. DSP Analysis: Convert time-domain audio to frequency peaks
        peaks = self._dsp.process(audio_chunk)

        # 2. Frequency Filter: Remove irrelevant frequencies early for performance
        filtered_peaks = self._freq_filter.filter_peaks(peaks)

        # 3. Event Generation: distinct tones from continuous spectral data
        events = self._generator.process(filtered_peaks, self._current_time)

        # 4. Pattern Matching: Buffer events and analyze windows
        for event in events:
            self._matcher.add_event(event)

        # Evaluate windows
        detected = False
        matches = self._matcher.evaluate(self._current_time)
        for match in matches:
            self._trigger_alarm(match)
            detected = True

        return detected

    def _trigger_alarm(self, match: PatternMatchEvent) -> None:
        """Handle a confirmed pattern match detection.

        Logs the alarm, triggers callbacks, and manages the alarm state reset.

        Args:
            match: The PatternMatchEvent detailing the detection.
        """
        logger.info(f"MATCH: {match.profile_name} (Cycle {match.cycle_count})")

        if not self._alarm_active:
            logger.critical("=" * 60)
            logger.critical(f"🚨 ALARM DETECTED: [{match.profile_name.upper()}] 🚨")
            logger.critical(f"Timestamp: {match.timestamp:.2f}s")
            logger.critical("=" * 60)

            self._alarm_active = True

            # Fire callbacks
            if self.on_detection:
                try:
                    self.on_detection(match.profile_name)
                except Exception as e:
                    logger.error(f"Error in on_detection callback: {e}")

            if self.on_match:
                try:
                    self.on_match(match)
                except Exception as e:
                    logger.error(f"Error in on_match callback: {e}")

            # Auto-reset after timeout to allow new detections
            def clear():
                time.sleep(10)  # Hardcoded cooldown for now
                if self._alarm_active:
                    logger.info("Auto-clearing alarm state.")
                    self._alarm_active = False

            threading.Thread(target=clear, daemon=True).start()

    def start(self) -> None:
        """Start the engine with built-in audio capture (blocking).

        This initializes the AudioListener and blocks the current thread,
        processing audio until stop() is called or a KeyboardInterrupt occurs.

        Raises:
            RuntimeError: If audio setup fails.
        """
        self._listener = AudioListener(self.audio_config, self.process_chunk)

        if not self._listener.setup():
            logger.error("Failed to setup audio listener")
            # In a real app, might want to raise an exception here
            return

        self._running = True

        try:
            self._listener.start()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.stop()

    def start_async(self) -> threading.Thread:
        """Start the engine in a background thread.

        Ideal for integrating the engine into a larger application (e.g., GUI or web server).

        Returns:
            The background thread object (already started).
        """
        thread = threading.Thread(target=self.start, daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        """Stop the engine and release audio resources.

        This signals the processing loop to exit and cleans up the PyAudio stream.
        """
        self._running = False

        if self._listener:
            self._listener.stop()
            self._listener.cleanup()
            self._listener = None

        logger.info("Engine stopped")

    @property
    def is_running(self) -> bool:
        """Check if the engine is currently running."""
        return self._running

    @property
    def alarm_active(self) -> bool:
        """Check if an alarm is currently active (cooldown period)."""
        return self._alarm_active
