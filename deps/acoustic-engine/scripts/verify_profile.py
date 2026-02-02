#!/usr/bin/env python3
"""
Verify Profile Tool
===================

A standalone CLI tool to test a specific audio file against a specific Alarm Profile YAML.
Useful for tuning parameters or verifying that a recorded alarm matches your config.

Usage:
    python scripts/verify_profile.py --audio recording.wav --profile my_config.yaml
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from acoustic_engine.config import DEFAULT_DROPOUT_TOLERANCE, DEFAULT_MIN_TONE_DURATION
from acoustic_engine.tester.display import Display
from acoustic_engine.tester.runner import TestRunner


def main():
    parser = argparse.ArgumentParser(description="Verify an alarm profile against an audio file.")
    parser.add_argument("--audio", "-a", required=True, help="Path to the .wav or .mp3 file")
    parser.add_argument("--profile", "-p", required=True, help="Path to the profile .yaml file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed debug output")
    parser.add_argument(
        "--high-res", action="store_true", help="Enable high-resolution analysis (11ms chunks)"
    )
    parser.add_argument(
        "--dropout", type=float, help="Override dropout tolerance (e.g. 0.1 for 100ms)"
    )

    args = parser.parse_args()

    # Check files
    audio_path = Path(args.audio)
    profile_path = Path(args.profile)

    if not audio_path.exists():
        print(f"Error: Audio file not found: {audio_path}")
        sys.exit(1)

    if not profile_path.exists():
        print(f"Error: Profile file not found: {profile_path}")
        sys.exit(1)

    print("=" * 60)
    print("🧪 VERIFY PROFILE")
    print(f"   Audio:   {audio_path.name}")
    print(f"   Profile: {profile_path.name}")
    print("=" * 60)

    # Configure logging
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Load defaults
    if args.high_res:
        min_tone_duration = 0.02  # 20ms minimum
        dropout_tolerance = args.dropout if args.dropout else 0.04  # Default 40ms, or user override
        print(f"ℹ️  Using High-Resolution Mode (Dropout: {dropout_tolerance}s)")
    else:
        min_tone_duration = DEFAULT_MIN_TONE_DURATION
        dropout_tolerance = args.dropout if args.dropout else DEFAULT_DROPOUT_TOLERANCE

    # Use TestRunner for nice output
    display = Display(verbose=args.verbose)
    runner = TestRunner(
        profile_path=profile_path,
        verbose=args.verbose,
        display=display,
        high_resolution=args.high_res,
        min_tone_duration=min_tone_duration,
        dropout_tolerance=dropout_tolerance,
    )

    try:
        runner.run_file(audio_path)
    except Exception as e:
        print(f"\n❌ Error running verification: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)

    # Summary
    matches = len(runner.results.detections)
    print("\n" + "-" * 60)
    if matches > 0:
        print(f"✅ SUCCESS: Found {matches} matching alarm pattern(s).")
        for i, det in enumerate(runner.results.detections):
            print(f"   {i + 1}. {det.profile_name} at {det.timestamp:.3f}s")
    else:
        print("❌ FAILURE: No matching patterns found.")
        print("\nPossible solutions:")
        print("1. Check if the audio actually contains the alarm.")
        print("2. Try running with --verbose to see what the engine 'hears'.")
        print("3. Check your profile frequency ranges (add ±50Hz tolerance).")
        print("4. Check your timing (duration) ranges (add ±0.1s tolerance).")
        if not args.high_res:
            print("5. Try running with --high-res if the beeps are very fast (<0.1s).")


if __name__ == "__main__":
    main()
