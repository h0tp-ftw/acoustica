"""Core audio detection logic using Universal Engine pipeline.

This module orchestrates:
1. SpectralMonitor (DSP Analysis)
2. EventGenerator (Peak -> Event conversion)
3. SequenceMatcher (Pattern matching)
"""

import numpy as np
import time
import logging
from typing import Callable, Optional, List, Union

# New Universal Engine Components (using bundled acoustic-engine)
from acoustic_engine.models import AlarmProfile, Range, Segment
from acoustic_engine.processing.dsp import SpectralMonitor
from acoustic_engine.analysis.generator import EventGenerator
from acoustic_engine.analysis.matcher import SequenceMatcher
from acoustic_engine.events import PatternMatchEvent

# Legacy config import
from detector.config import DetectorProfile

logger = logging.getLogger(__name__)


class PatternDetector:
    """Acoustic alarm detector using the Universal Alarm Engine."""

    def __init__(
        self,
        config_object: Union[
            DetectorProfile, List[DetectorProfile], List[AlarmProfile]
        ],
        sample_rate: int,
        chunk_size: int,
        on_detection: Optional[Callable[[bool], None]] = None,
    ):
        """Initialize the detector pipeline.

        Args:
            config_object: Configuration profile(s)
            sample_rate: Audio sample rate
            chunk_size: Audio chunk size
            on_detection: Callback for alarm state changes
        """
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.on_detection = on_detection
        self.alarm_active = False

        # Convert Legacy Config if necessary
        self.profiles: List[AlarmProfile] = []

        # Helper to normalize input to a list
        configs = config_object if isinstance(config_object, list) else [config_object]

        for p in configs:
            if isinstance(p, DetectorProfile):
                self.profiles.append(self._convert_legacy_profile(p))
            elif isinstance(p, AlarmProfile):
                self.profiles.append(p)
            else:
                logger.warning(f"Unknown config type: {type(p)}")

        if self.profiles:
            self.name = (
                self.profiles[0].name if len(self.profiles) == 1 else "CombinedDetector"
            )
        else:
            self.name = "EmptyDetector"

        # Initialize Pipeline Components
        self.dsp = SpectralMonitor(sample_rate, chunk_size)
        self.generator = EventGenerator(sample_rate, chunk_size)
        self.matcher = SequenceMatcher(self.profiles)

        # Timing context
        self.current_time = 0.0

        logger.info(
            f"Universal Detector [{self.name}] initialized with {len(self.profiles)} profiles."
        )

    def _convert_legacy_profile(self, p: DetectorProfile) -> AlarmProfile:
        """Convert a legacy config into a Universal AlarmProfile."""
        segments = []

        # We need to construct [Tone, Silence] * N
        for _ in range(p.beep_count):
            # Add Tone Step
            segments.append(
                Segment(
                    type="tone",
                    frequency=Range(
                        p.target_frequency - p.frequency_tolerance,
                        p.target_frequency + p.frequency_tolerance,
                    ),
                    duration=Range(p.beep_duration_min, p.beep_duration_max),
                    min_magnitude=p.min_magnitude_threshold,
                )
            )
            # Add Silence Step (Inter-beep pause)
            segments.append(
                Segment(
                    type="silence",
                    duration=Range(p.pause_duration_min, p.pause_duration_max),
                )
            )

        return AlarmProfile(
            name=p.name,
            segments=segments,
            confirmation_cycles=p.confirmation_cycles,
            reset_timeout=p.pattern_timeout,
        )

    def process(self, audio_chunk: np.ndarray) -> bool:
        """Process an audio chunk through the pipeline."""

        # 0. Time Keeping (approximate based on chunk flow)
        chunk_duration = self.chunk_size / self.sample_rate
        self.current_time += chunk_duration

        # 1. DSP Analysis (Get Peaks)
        peaks = self.dsp.process(audio_chunk)

        # 2. Event Generation (Get Events)
        events = self.generator.process(peaks, self.current_time)

        # 3. Pattern Matching (Check Events)
        detected = False

        if events:
            for event in events:
                matches = self.matcher.process(event)
                if matches:
                    self._trigger_alarm(matches[0])
                    detected = True

        return detected

    def _trigger_alarm(self, match: PatternMatchEvent) -> None:
        """Trigger alarm detection."""
        # Only trigger if not already active to avoid spamming callbacks
        # But we DO want to log every match cycle usually?
        logger.info(f"MATCH: {match.profile_name} (Cycle {match.cycle_count})")

        if not self.alarm_active:
            logger.critical("=" * 60)
            logger.critical(
                f"🚨 UNIVERSAL ENGINE: [{match.profile_name.upper()}] ALARM ACTIVE! 🚨"
            )
            logger.critical(f"Timestamp: {match.timestamp:.2f}s")
            logger.critical("=" * 60)

            self.alarm_active = True
            if self.on_detection:
                self.on_detection(True)

            # Auto-reset logic (simple timer for now)
            import threading

            def clear():
                time.sleep(10)
                if self.alarm_active:
                    logger.info(f"[{self.name}] Auto-clearing alarm state.")
                    self.alarm_active = False
                    if self.on_detection:
                        self.on_detection(False)

            threading.Thread(target=clear, daemon=True).start()


# Legacy alias
AlarmDetector = PatternDetector
