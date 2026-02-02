"""Parallel Engine - Orchestrates multiple isolated Engine instances.

This module implements the Parallel Pipeline architecture, where each AlarmProfile
runs in its own dedicated Engine instance with its own tuning parameters.
This ensures that optimization for one alarm type (e.g. Smoke) does not negatively
impact others (e.g. CO).
"""

import logging
import threading
from typing import Callable, List, Optional, Tuple, Union

import numpy as np

from .config import AudioSettings, EngineConfig, GlobalConfig
from .engine import Engine
from .events import PatternMatchEvent
from .input.listener import AudioListener
from .models import AlarmProfile

logger = logging.getLogger(__name__)


class ParallelEngine:
    """A collection of Engine instances running in parallel.

    Routes audio input to multiple engines, each configured for a specific profile.
    Aggregates callbacks from all instances.
    """

    def __init__(
        self,
        pipelines: List[Union[AlarmProfile, Tuple[AlarmProfile, EngineConfig]]],
        audio_config: Optional[AudioSettings] = None,
        on_detection: Optional[Callable[[str], None]] = None,
        on_match: Optional[Callable[[PatternMatchEvent], None]] = None,
    ):
        """Initialize the parallel engine.

        Args:
            pipelines: List of items to run. Can be:
                      - AlarmProfile: Will auto-generate a config for this profile.
                      - (AlarmProfile, EngineConfig): Will use the provided config.
            audio_config: Master audio capture settings.
            on_detection: Aggregated simple callback.
            on_match: Aggregated detailed callback.
        """
        self.pipelines = pipelines
        self.audio_config = audio_config or AudioSettings()
        self.on_detection = on_detection
        self.on_match = on_match

        # Create isolated engine instances for each profile
        self.engines: List[Engine] = []

        logger.info(f"Initializing ParallelEngine with {len(pipelines)} pipelines:")

        for item in pipelines:
            if isinstance(item, AlarmProfile):
                profile = item
                # Create a bespoke config for this specific profile
                engine_config = EngineConfig.from_single_profile(
                    profile,
                    sample_rate=self.audio_config.sample_rate,
                    chunk_size=self.audio_config.chunk_size,
                )
            else:
                # Explicit config provided
                profile, engine_config = item

            logger.info(
                f"  - Pipeline '{profile.name}': dropout={engine_config.dropout_tolerance:.3f}s, min_tone={engine_config.min_tone_duration:.3f}s, sensitivity={engine_config.min_magnitude:.1f}"
            )

            # Create the engine instance
            engine = Engine(
                profiles=[profile],  # Single profile per engine
                audio_config=self.audio_config,  # Shared audio settings
                engine_config=engine_config,
                on_detection=self._handle_detection,
                on_match=self._handle_match,
            )
            self.engines.append(engine)

        # Audio listener (shared)
        self._listener: Optional[AudioListener] = None
        self._running = False

        # Deduplication lock for callbacks if needed (though engines are sequential in process_chunk)
        self._callback_lock = threading.Lock()

    def _handle_detection(self, profile_name: str) -> None:
        """Internal callback to route detections to the main callback."""
        if self.on_detection:
            with self._callback_lock:
                self.on_detection(profile_name)

    def _handle_match(self, match: PatternMatchEvent) -> None:
        """Internal callback to route matches to the main callback."""
        if self.on_match:
            with self._callback_lock:
                self.on_match(match)

    def process_chunk(self, audio_chunk: np.ndarray) -> bool:
        """Process a chunk of audio through ALL pipelines.

        Args:
            audio_chunk: Raw audio samples.

        Returns:
            True if ANY engine detected an alarm in this chunk.
        """
        any_detected = False

        # Route audio to all engines
        # Since these are lightweight logical engines, we can run them sequentially
        # in the same thread loop without blocking the audio stream.
        # (Benchmark showed >400k chunks/sec throughput, so 2-10 engines is trivial)
        for engine in self.engines:
            if engine.process_chunk(audio_chunk):
                any_detected = True

        return any_detected

    def start(self) -> None:
        """Start the parallel engine (blocking)."""
        self._listener = AudioListener(self.audio_config, self.process_chunk)

        if not self._listener.setup():
            logger.error("Failed to setup audio listener")
            return

        self._running = True
        logger.info("ParallelPipeline started. Listening...")

        try:
            self._listener.start()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.stop()

    def start_async(self) -> threading.Thread:
        """Start in a background thread."""
        thread = threading.Thread(target=self.start, daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        """Stop all engines and release resources."""
        self._running = False
        if self._listener:
            self._listener.stop()
            self._listener.cleanup()
            self._listener = None

        logger.info("ParallelPipeline stopped")

    @classmethod
    def from_config(cls, config: GlobalConfig) -> "ParallelEngine":
        """Create from GlobalConfig."""
        # Initialize logging
        logging.getLogger().setLevel(config.system.log_level)

        return cls(
            profiles=config.profiles,
            audio_config=config.audio,
            # Config.engine is ignored here as we generate per-profile configs
        )
