"""Add-on entry point: wire add-on options into the acoustic engine.

Flow: read options -> build AlarmProfiles -> run a ParallelEngine on the mic ->
each confirmed detection is pushed to Home Assistant by the HABridge.

The engine owns audio capture, DSP, and matching; we just connect it to Home
Assistant. Run with ``python3 -m detector.main``.
"""

import logging
import signal
import sys

from acoustic_engine.parallel_engine import ParallelEngine

from detector.config import load_app_config
from detector.ha_bridge import HABridge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("acoustic-addon")


def main() -> None:
    config = load_app_config()

    if config.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("acoustic_engine").setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info("Acoustic Alarm Detector add-on")
    logger.info("=" * 60)

    if not config.detectors:
        logger.error(
            "No usable detectors configured. Add at least one detector with a "
            "'preset', 'profile', or 'learn' source in the add-on options."
        )
        sys.exit(1)

    for spec in config.detectors:
        logger.info(
            "Detector: %r [device_class=%s, %d segments, %d cycle(s)]",
            spec.profile.name,
            spec.device_class,
            len(spec.profile.segments),
            spec.profile.confirmation_cycles,
        )
    logger.info(
        "Audio: %d Hz, device=%s | hold=%.0fs",
        config.audio.sample_rate,
        config.audio.device_index if config.audio.device_index is not None else "default",
        config.hold_seconds,
    )

    bridge = HABridge(
        device_classes=config.device_classes,
        hold_seconds=config.hold_seconds,
    )
    bridge.setup()

    engine = ParallelEngine(
        pipelines=config.profiles,
        audio_config=config.audio,
        on_detection=bridge.on_detection,
    )

    def handle_signal(signum, _frame):
        logger.info("Received signal %s — shutting down.", signum)
        engine.stop()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logger.info("Listening on the microphone... (Ctrl+C to stop)")
    try:
        engine.start()  # blocking until stop()/KeyboardInterrupt
    except Exception as e:  # pragma: no cover - top-level safety net
        logger.error("Fatal error in detection loop: %s", e, exc_info=True)
    finally:
        bridge.shutdown()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    main()
