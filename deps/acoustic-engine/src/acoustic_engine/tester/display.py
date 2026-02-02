"""Display utilities for the profile tester."""

import sys
from typing import Optional


class Colors:
    """ANSI color codes for terminal output."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Catppuccin-inspired colors
    RED = "\033[38;5;211m"  # Matches detection alert
    GREEN = "\033[38;5;157m"  # Success/match
    YELLOW = "\033[38;5;223m"  # Warning
    BLUE = "\033[38;5;117m"  # Info
    MAGENTA = "\033[38;5;183m"  # Tone events
    CYAN = "\033[38;5;159m"  # Timestamps
    GRAY = "\033[38;5;245m"  # Dim text
    WHITE = "\033[38;5;255m"  # Bright text

    # Background
    BG_RED = "\033[48;5;52m"
    BG_GREEN = "\033[48;5;22m"


class Display:
    """Handles formatted output for the tester."""

    def __init__(self, verbose: bool = False, use_colors: bool = True):
        self.verbose = verbose
        self.use_colors = use_colors and sys.stdout.isatty()

    def _c(self, color: str) -> str:
        """Return color code if colors enabled."""
        return color if self.use_colors else ""

    def header(self):
        """Print application header."""
        print()
        print(
            f"{self._c(Colors.BOLD)}{self._c(Colors.MAGENTA)}╔══════════════════════════════════════════════════════════╗{self._c(Colors.RESET)}"
        )
        print(
            f"{self._c(Colors.BOLD)}{self._c(Colors.MAGENTA)}║{self._c(Colors.RESET)}  🧪 {self._c(Colors.WHITE)}{self._c(Colors.BOLD)}Acoustic Alarm Engine - Profile Tester{self._c(Colors.RESET)}           {self._c(Colors.MAGENTA)}║{self._c(Colors.RESET)}"
        )
        print(
            f"{self._c(Colors.BOLD)}{self._c(Colors.MAGENTA)}╚══════════════════════════════════════════════════════════╝{self._c(Colors.RESET)}"
        )
        print()

    def info(self, message: str):
        """Print info message."""
        print(f"{self._c(Colors.BLUE)}ℹ{self._c(Colors.RESET)} {message}")

    def success(self, message: str):
        """Print success message."""
        print(f"{self._c(Colors.GREEN)}✓{self._c(Colors.RESET)} {message}")

    def warning(self, message: str):
        """Print warning message."""
        print(f"{self._c(Colors.YELLOW)}⚠{self._c(Colors.RESET)} {message}")

    def error(self, message: str):
        """Print error message."""
        print(f"{self._c(Colors.RED)}✗{self._c(Colors.RESET)} {message}")

    def detection(self, profile_name: str, cycle_count: int, timestamp: float):
        """Print a detection event."""
        time_str = self._format_time(timestamp)
        print()
        print(
            f"{self._c(Colors.BG_RED)}{self._c(Colors.WHITE)}{self._c(Colors.BOLD)} 🚨 DETECTION {self._c(Colors.RESET)} "
            f"{self._c(Colors.CYAN)}{time_str}{self._c(Colors.RESET)} "
            f"{self._c(Colors.BOLD)}{profile_name}{self._c(Colors.RESET)} "
            f"{self._c(Colors.GRAY)}({cycle_count} cycles){self._c(Colors.RESET)}"
        )
        print()

    def tone_event(
        self,
        timestamp: float,
        frequency: float,
        duration: float,
        matched: bool = False,
        segment_idx: Optional[int] = None,
    ):
        """Print a tone event (verbose mode)."""
        if not self.verbose:
            return

        time_str = self._format_time(timestamp)
        match_str = ""
        if matched and segment_idx is not None:
            match_str = f" {self._c(Colors.GREEN)}✓ seg[{segment_idx}]{self._c(Colors.RESET)}"
        elif matched:
            match_str = f" {self._c(Colors.GREEN)}✓{self._c(Colors.RESET)}"

        print(
            f"  {self._c(Colors.CYAN)}{time_str}{self._c(Colors.RESET)} "
            f"{self._c(Colors.MAGENTA)}🎵 Tone{self._c(Colors.RESET)} "
            f"{self._c(Colors.WHITE)}{frequency:.0f}Hz{self._c(Colors.RESET)} "
            f"{self._c(Colors.GRAY)}({duration:.2f}s){self._c(Colors.RESET)}"
            f"{match_str}"
        )

    def silence_event(
        self,
        timestamp: float,
        duration: float,
        matched: bool = False,
        segment_idx: Optional[int] = None,
    ):
        """Print a silence event (verbose mode)."""
        if not self.verbose:
            return

        time_str = self._format_time(timestamp)
        match_str = ""
        if matched and segment_idx is not None:
            match_str = f" {self._c(Colors.GREEN)}✓ seg[{segment_idx}]{self._c(Colors.RESET)}"
        elif matched:
            match_str = f" {self._c(Colors.GREEN)}✓{self._c(Colors.RESET)}"

        print(
            f"  {self._c(Colors.CYAN)}{time_str}{self._c(Colors.RESET)} "
            f"{self._c(Colors.GRAY)}⏸ Silence{self._c(Colors.RESET)} "
            f"{self._c(Colors.GRAY)}({duration:.2f}s){self._c(Colors.RESET)}"
            f"{match_str}"
        )

    def cycle_complete(self, profile_name: str, cycle: int, total: int, timestamp: float):
        """Print cycle completion (verbose mode)."""
        if not self.verbose:
            return

        time_str = self._format_time(timestamp)
        print(
            f"  {self._c(Colors.CYAN)}{time_str}{self._c(Colors.RESET)} "
            f"{self._c(Colors.YELLOW)}🔄 Cycle {cycle}/{total}{self._c(Colors.RESET)} "
            f"{self._c(Colors.GRAY)}{profile_name}{self._c(Colors.RESET)}"
        )

    def profile_loaded(self, name: str, segments: int, cycles: int):
        """Print profile load message."""
        print(
            f"  {self._c(Colors.GREEN)}▸{self._c(Colors.RESET)} "
            f"{self._c(Colors.WHITE)}{name}{self._c(Colors.RESET)} "
            f"{self._c(Colors.GRAY)}({segments} segments, {cycles} cycles){self._c(Colors.RESET)}"
        )

    def noise_config(self, noise_type: str, level: float):
        """Print noise configuration."""
        if level > 0:
            bar_width = 20
            filled = int(level * bar_width)
            bar = "█" * filled + "░" * (bar_width - filled)
            print(
                f"  {self._c(Colors.YELLOW)}🔊 Noise:{self._c(Colors.RESET)} "
                f"{noise_type} {self._c(Colors.GRAY)}[{bar}]{self._c(Colors.RESET)} "
                f"{level * 100:.0f}%"
            )

    def results_header(self):
        """Print results section header."""
        print()
        print(f"{self._c(Colors.BOLD)}{'─' * 60}{self._c(Colors.RESET)}")
        print(f"{self._c(Colors.BOLD)}📊 Results{self._c(Colors.RESET)}")
        print(f"{self._c(Colors.BOLD)}{'─' * 60}{self._c(Colors.RESET)}")

    def results_summary(self, detections: int, duration: float, profiles_tested: int):
        """Print results summary."""
        rate = detections / duration * 60 if duration > 0 else 0

        if detections > 0:
            status = f"{self._c(Colors.GREEN)}✓ PASS{self._c(Colors.RESET)}"
        else:
            status = f"{self._c(Colors.YELLOW)}○ No detections{self._c(Colors.RESET)}"

        print(f"  Status: {status}")
        print(f"  Detections: {self._c(Colors.WHITE)}{detections}{self._c(Colors.RESET)}")
        print(f"  Duration: {self._c(Colors.GRAY)}{duration:.1f}s{self._c(Colors.RESET)}")
        print(f"  Profiles: {self._c(Colors.GRAY)}{profiles_tested}{self._c(Colors.RESET)}")
        if detections > 0:
            print(f"  Rate: {self._c(Colors.GRAY)}{rate:.1f}/min{self._c(Colors.RESET)}")
        print()

    def _format_time(self, timestamp: float) -> str:
        """Format timestamp as MM:SS.mmm."""
        minutes = int(timestamp // 60)
        seconds = timestamp % 60
        return f"{minutes:02d}:{seconds:06.3f}"

    def separator(self):
        """Print a visual separator."""
        print(f"{self._c(Colors.GRAY)}{'─' * 60}{self._c(Colors.RESET)}")
