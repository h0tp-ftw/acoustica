"""Profile Tester - Test alarm profiles with the real engine.

Run with: python -m acoustic_engine.tester

Features:
- Load and test YAML profiles
- Live microphone or audio file input
- Noise mixing for specificity testing
- Detailed event logging
"""

import argparse
import sys
from pathlib import Path
from typing import Optional


def main(
    profile_path: Optional[str] = None,
    audio_file: Optional[str] = None,
    noise_level: float = 0.0,
    noise_type: str = "white",
    live: bool = False,
    verbose: bool = False,
    duration: float = 30.0,
    high_resolution: bool = False,
):
    """Run the profile tester.

    Args:
        profile_path: Path to YAML profile file or directory
        audio_file: Path to audio file to test (WAV/MP3/OGG/FLAC)
        noise_level: Noise mixing level 0.0-1.0
        noise_type: Type of noise (white, pink, brown)
        live: Use live microphone input
        verbose: Show detailed event logging
        duration: Duration for live mode in seconds
        high_resolution: Use smaller gap tolerance for fast patterns
    """
    from .display import Display
    from .runner import TestRunner

    # Enable debug logging if verbose mode
    if verbose:
        import logging

        logging.basicConfig(level=logging.DEBUG, format="  %(message)s")
        # Enable debug logging for the matcher specifically
        logging.getLogger("acoustic_engine.analysis.windowed_matcher").setLevel(logging.DEBUG)
        logging.getLogger("acoustic_engine.analysis.generator").setLevel(logging.DEBUG)

    display = Display(verbose=verbose)

    display.header()

    # Validate inputs
    if not profile_path:
        display.error("No profile specified. Use --profile <path>")
        sys.exit(1)

    if not live and not audio_file:
        display.error("Specify --live for microphone or --audio <file> for file input")
        sys.exit(1)

    # Load profiles
    profile_path = Path(profile_path)
    if not profile_path.exists():
        display.error(f"Profile not found: {profile_path}")
        sys.exit(1)

    # Create runner
    runner = TestRunner(
        profile_path=profile_path,
        noise_level=noise_level,
        noise_type=noise_type,
        verbose=verbose,
        display=display,
        high_resolution=high_resolution,
    )

    try:
        if live:
            if duration <= 0:
                display.info("Starting continuous live test...")
                display.info("Press Ctrl+C to stop")
            else:
                display.info(f"Starting live test for {duration}s...")
                display.info("Press Ctrl+C to stop early")
            runner.run_live(duration=duration)
        else:
            audio_path = Path(audio_file)
            if not audio_path.exists():
                display.error(f"Audio file not found: {audio_path}")
                sys.exit(1)
            display.info(f"Testing audio file: {audio_path}")
            runner.run_file(audio_path)

        # Show results
        runner.show_results()

    except KeyboardInterrupt:
        display.info("\nTest interrupted")
        runner.show_results()
    except Exception as e:
        display.error(f"Error: {e}")
        if verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


def cli():
    """Command-line interface entry point."""
    parser = argparse.ArgumentParser(
        description="Test alarm profiles with the actual detection engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test a profile with an audio file
  python -m acoustic_engine.tester --profile profiles/smoke_alarm.yaml --audio sample.wav

  # Continuous live mode (runs forever until Ctrl+C)
  python -m acoustic_engine.tester --profile profiles/smoke_alarm.yaml --live

  # Live microphone test with time limit
  python -m acoustic_engine.tester --profile profiles/ --live --duration 60

  # Test with noise mixing
  python -m acoustic_engine.tester --profile profiles/co_detector.yaml --audio sample.wav --noise 0.3 --noise-type white

  # Verbose mode for debugging
  python -m acoustic_engine.tester --profile profiles/smoke_alarm.yaml --audio sample.wav -v
        """,
    )

    parser.add_argument(
        "-p",
        "--profile",
        type=str,
        required=True,
        help="Path to YAML profile file or directory containing profiles",
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--live",
        action="store_true",
        help="Use live microphone input",
    )
    input_group.add_argument(
        "-a",
        "--audio",
        type=str,
        help="Path to audio file (WAV format)",
    )

    parser.add_argument(
        "-n",
        "--noise",
        type=float,
        default=0.0,
        help="Noise mixing level 0.0-1.0 (default: 0.0)",
    )
    parser.add_argument(
        "--noise-type",
        type=str,
        choices=["white", "pink", "brown"],
        default="white",
        help="Type of noise to mix (default: white)",
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=float,
        default=0,
        help="Duration for live mode in seconds (default: 0 = continuous until Ctrl+C)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed event logging",
    )
    parser.add_argument(
        "--high-res",
        action="store_true",
        help="High-resolution mode for fast patterns (<100ms gaps)",
    )

    args = parser.parse_args()

    main(
        profile_path=args.profile,
        audio_file=args.audio,
        noise_level=args.noise,
        noise_type=args.noise_type,
        live=args.live,
        verbose=args.verbose,
        duration=args.duration,
        high_resolution=args.high_res,
    )


if __name__ == "__main__":
    cli()
