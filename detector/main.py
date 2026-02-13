"""Main application entry point.

Orchestrates the three-part architecture:
- Listener: Audio capture
- Detector: Pattern recognition
- Sensor: Home Assistant integration
"""

import logging
import sys
import signal
from typing import List

from config import DetectorConfig, AudioSettings
from listener import AudioListener, AudioConfig
from detector import PatternDetector
from sensor import SensorManager, SensorProfile

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class DetectorApp:
    """Main application orchestrator."""

    def __init__(self):
        """Initialize the application."""
        self.config: DetectorConfig = None
        self.listener: AudioListener = None
        self.detectors: List[PatternDetector] = []
        self.sensor_manager: SensorManager = None
        self.running = False

    def setup(self) -> bool:
        """Initialize all components.

        Returns:
            True if setup succeeded, False otherwise
        """
        # Load configuration
        self.config = DetectorConfig.from_environment()
        self.config.log_config()

        # Create sensor profiles from detector profiles
        sensor_profiles = [
            SensorProfile(
                name=p.name,
                device_class=p.device_class,
            )
            for p in self.config.profiles
        ]

        # Initialize Sensor Manager (HA communication)
        self.sensor_manager = SensorManager(
            device_name=self.config.device_name,
            profiles=sensor_profiles,
        )
        if not self.sensor_manager.setup():
            logger.warning(
                "⚠️ Sensor manager setup failed - will retry on alarm detection"
            )

        # Initialize Detectors (one per profile)
        for profile in self.config.profiles:
            # Create detection callback that routes to sensor manager
            callback = self.sensor_manager.create_detection_callback(profile.name)

            detector = PatternDetector(
                profile=profile,
                sample_rate=self.config.audio.sample_rate,
                chunk_size=self.config.audio.chunk_size,
                on_detection=callback,
            )
            self.detectors.append(detector)

        logger.info(f"✅ Created {len(self.detectors)} detector(s)")

        # Initialize Listener (audio capture)
        audio_config = AudioConfig(
            sample_rate=self.config.audio.sample_rate,
            chunk_size=self.config.audio.chunk_size,
            channels=self.config.audio.channels,
            device_index=self.config.audio.device_index,
        )

        self.listener = AudioListener(
            config=audio_config,
            on_audio_chunk=self._on_audio_chunk,
        )

        if not self.listener.setup():
            logger.error("❌ Failed to initialize audio listener")
            return False

        logger.info("✅ Audio listener initialized")

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        return True

    def _on_audio_chunk(self, audio_chunk) -> None:
        """Callback for processing audio chunks through all detectors."""
        for detector in self.detectors:
            detector.process(audio_chunk)

    def _signal_handler(self, signum, frame) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}. Shutting down...")
        self.running = False
        self.listener.stop()

    def run(self) -> None:
        """Start the detection loop."""
        self.running = True
        logger.info("=" * 50)
        logger.info("🎤 ACOUSTIC ALARM DETECTOR - RUNNING")
        logger.info("=" * 50)

        try:
            self.listener.start()
        except KeyboardInterrupt:
            logger.info("Shutdown requested by user")
        except Exception as e:
            logger.error(f"FATAL: Error in main loop: {e}", exc_info=True)
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        """Clean up all resources."""
        logger.info("Cleaning up resources...")

        if self.listener:
            self.listener.cleanup()

        if self.sensor_manager:
            self.sensor_manager.cleanup()

        logger.info("✅ Shutdown complete")


def main():
    """Entry point."""
    app = DetectorApp()

    if not app.setup():
        logger.error("Setup failed. Exiting.")
        sys.exit(1)

    app.run()


if __name__ == "__main__":
    main()
