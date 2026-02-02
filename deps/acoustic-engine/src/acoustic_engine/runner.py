import argparse
import logging
import sys
from typing import List, Tuple

from .config import EngineConfig, GlobalConfig
from .models import AlarmProfile
from .parallel_engine import ParallelEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("runner")


def main():
    parser = argparse.ArgumentParser(description="Acoustic Alarm Engine Runner")
    parser.add_argument(
        "-c",
        "--config",
        action="append",
        required=True,
        help="Path to YAML configuration file. Can be specified multiple times.",
    )
    args = parser.parse_args()

    # 1. Load all configurations
    configs: List[GlobalConfig] = []
    for config_path in args.config:
        try:
            logger.info(f"Loading config: {config_path}")
            cfg = GlobalConfig.load(config_path)
            configs.append(cfg)
        except Exception as e:
            logger.error(f"Failed to load {config_path}: {e}")
            sys.exit(1)

    if not configs:
        logger.error("No valid configurations loaded.")
        sys.exit(1)

    # 2. Smart Negotiation for Audio Settings
    # Find the configuration with the highest sample rate
    # We prioritize sample rate for quality.
    best_audio_config = configs[0].audio

    for cfg in configs[1:]:
        if cfg.audio.sample_rate > best_audio_config.sample_rate:
            best_audio_config = cfg.audio
            logger.info(
                f"Upgrading Global Audio Context to {best_audio_config.sample_rate}Hz (found in config)"
            )

    logger.info("=" * 50)
    logger.info(
        f"GLOBAL AUDIO CONTEXT: {best_audio_config.sample_rate}Hz, {best_audio_config.chunk_size} samples"
    )
    logger.info("=" * 50)

    # 3. Build Parallel Pipelines
    pipelines: List[Tuple[AlarmProfile, EngineConfig]] = []

    for i, cfg in enumerate(configs):
        original_source = args.config[i]

        # Determine effective engine config for this file
        # This preserves the user's specific tuning (sensitivity, thresholds)
        # BUT overrides the audio geometry to match the Global Context.

        # We need to apply the global sample rate/chunk size to the engine config
        # However, simply overwriting them might invalidate calculated fields (like min_sharpness or tolerances?)
        # Actually, EngineConfig fields are mostly independent, EXCEPT frequency_tolerance might need scaling if chunk size changed drastically.
        # But generally, higher sample rate is safer.

        # If the config had specific engine settings (loaded from YAML), we use them.
        # But we must update sample_rate and chunk_size.

        base_engine_config = cfg.engine

        # Check if we are forcing a change
        if base_engine_config.sample_rate != best_audio_config.sample_rate:
            logger.warning(
                f"[{original_source}] Overriding sample_rate {base_engine_config.sample_rate} -> {best_audio_config.sample_rate}"
            )
            base_engine_config.sample_rate = best_audio_config.sample_rate

        if base_engine_config.chunk_size != best_audio_config.chunk_size:
            logger.warning(
                f"[{original_source}] Overriding chunk_size {base_engine_config.chunk_size} -> {best_audio_config.chunk_size}"
            )
            base_engine_config.chunk_size = best_audio_config.chunk_size

        # Now creating pipelines for each profile in this config
        for profile in cfg.profiles:
            # We clone the base engine config for each profile
            # This ensures they share the file's "Engine" settings (like sensitivity)
            # but we could also allow per-profile optimization if we wanted.
            # For this "Runner" architecture, the YAML defines the engine.

            # Use dataclass replace or manual copy if needed, but EngineConfig is mutable dataclass.
            # We'll use a new instance to be safe if we modify it later.
            import copy

            final_config = copy.copy(base_engine_config)

            # Recalculate resolution-dependent fields?
            # Ideally the user provided specific tuning.
            # If they didn't (defaults), we should perhaps re-run calculation?
            # But the user asked for "Separate Runners" where they define the config.
            # So we trust the loaded `cfg.engine` values, just patching audio.

            pipelines.append((profile, final_config))
            logger.info(
                f"  + Added Pipeline: {profile.name} (Sensitivity: {final_config.min_magnitude})"
            )

    # 4. Start Parallel Engine
    engine = ParallelEngine(
        pipelines=pipelines,
        audio_config=best_audio_config,
        on_detection=lambda name: logger.info(f"🚨 DETECTED: {name}"),
        on_match=lambda match: logger.info(
            f"match details: {match.profile_name} cycle={match.cycle_count}"
        ),
    )

    try:
        engine.start()
    except KeyboardInterrupt:
        logger.info("Stopping...")
        engine.stop()


if __name__ == "__main__":
    main()
