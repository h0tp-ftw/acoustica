"""Test runner for profile validation using the real engine."""

import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from ..analysis.generator import EventGenerator
from ..analysis.windowed_matcher import WindowedMatcher
from ..config import DEFAULT_DROPOUT_TOLERANCE, DEFAULT_MIN_TONE_DURATION, AudioSettings
from ..events import PatternMatchEvent, ToneEvent
from ..models import AlarmProfile
from ..processing.dsp import SpectralMonitor
from ..processing.filter import FrequencyFilter
from ..profiles import load_profiles_from_yaml
from .display import Display
from .mixer import AudioMixer


@dataclass
class TestResults:
    """Results from a test run."""

    detections: List[PatternMatchEvent] = field(default_factory=list)
    tone_events: List[ToneEvent] = field(default_factory=list)
    duration: float = 0.0
    profiles_tested: int = 0


class TestRunner:
    """Runs detection tests using the actual engine pipeline."""

    def __init__(
        self,
        profile_path: Path,
        noise_level: float = 0.0,
        noise_type: str = "white",
        verbose: bool = False,
        display: Optional[Display] = None,
        sample_rate: int = 44100,
        chunk_size: Optional[int] = None,
        high_resolution: bool = False,
        min_magnitude: float = 0.05,
        min_tone_duration: Optional[float] = None,
        dropout_tolerance: Optional[float] = None,
    ):
        self.noise_level = noise_level
        self.noise_type = noise_type
        self.verbose = verbose
        self.display = display or Display(verbose=verbose)
        self.high_resolution = high_resolution

        # Resolve chunk size from defaults if not provided
        if chunk_size is None:
            chunk_size = AudioSettings().chunk_size

        # High-resolution mode defaults
        if high_resolution:
            default_chunk = 512
            default_min_dur = 0.02
            default_dropout = 0.04
            self.display.info("High-resolution mode enabled")
        else:
            default_chunk = None  # Use global default
            default_min_dur = DEFAULT_MIN_TONE_DURATION
            default_dropout = DEFAULT_DROPOUT_TOLERANCE

        if high_resolution and chunk_size == AudioSettings().chunk_size:
            chunk_size = 512

        # Use provided values or defaults
        min_tone_duration = min_tone_duration if min_tone_duration is not None else default_min_dur
        dropout_tolerance = dropout_tolerance if dropout_tolerance is not None else default_dropout

        self.display.info(f"Config: min_dur={min_tone_duration}s, dropout={dropout_tolerance}s")

        self.sample_rate = sample_rate
        self.chunk_size = chunk_size

        # Load profiles
        self.profiles = self._load_profiles(profile_path)

        # Initialize engine components
        self.dsp = SpectralMonitor(sample_rate, chunk_size, min_magnitude=min_magnitude)
        self.freq_filter = FrequencyFilter(self.profiles)
        self.generator = EventGenerator(
            sample_rate,
            chunk_size,
            min_tone_duration=min_tone_duration,
            dropout_tolerance=dropout_tolerance,
        )
        self.matcher = WindowedMatcher(self.profiles)
        self.mixer = AudioMixer(sample_rate)

        # Log the filter configuration
        if self.freq_filter.freq_ranges:
            ranges_str = ", ".join(
                f"{fmin:.0f}-{fmax:.0f}Hz" for fmin, fmax in self.freq_filter.freq_ranges
            )
            self.display.info(f"Frequency filter: {ranges_str}")

        # Results
        self.results = TestResults(profiles_tested=len(self.profiles))

    def _load_profiles(self, path: Path) -> List[AlarmProfile]:
        """Load profiles from file or directory."""
        profiles = []

        self.display.info(f"Loading profiles from: {path}")

        if path.is_dir():
            # Load all YAML files in directory
            yaml_files = list(path.glob("*.yaml")) + list(path.glob("*.yml"))
            for yaml_file in yaml_files:
                try:
                    loaded = load_profiles_from_yaml(yaml_file)
                    profiles.extend(loaded)
                except Exception as e:
                    self.display.warning(f"Failed to load {yaml_file}: {e}")
        else:
            profiles = load_profiles_from_yaml(path)

        if not profiles:
            raise ValueError(f"No profiles found at {path}")

        for p in profiles:
            self.display.profile_loaded(p.name, len(p.segments), p.confirmation_cycles)

        self.display.noise_config(self.noise_type, self.noise_level)

        return profiles

    def run_file(self, audio_path: Path):
        """Run detection test on an audio file.

        Supports WAV, MP3, OGG, FLAC, and other formats.
        WAV uses built-in wave module; other formats require pydub + ffmpeg.

        Args:
            audio_path: Path to audio file
        """
        self.display.separator()

        # Load audio based on file extension
        suffix = audio_path.suffix.lower()

        if suffix == ".wav":
            audio, file_sample_rate = self._load_wav(audio_path)
        else:
            audio, file_sample_rate = self._load_with_pydub(audio_path)

        # Resample if needed (simple nearest-neighbor)
        if file_sample_rate != self.sample_rate:
            self.display.warning(f"Resampling from {file_sample_rate}Hz to {self.sample_rate}Hz")
            ratio = self.sample_rate / file_sample_rate
            new_length = int(len(audio) * ratio)
            indices = np.round(np.linspace(0, len(audio) - 1, new_length)).astype(int)
            audio = audio[indices]

        # Convert to float for noise mixing
        audio_float = audio.astype(np.float32) / 32768.0

        # Apply noise mixing
        if self.noise_level > 0:
            audio_float = self.mixer.mix_noise(
                audio_float, noise_type=self.noise_type, level=self.noise_level
            )

        # Convert back to int16 for processing
        audio = (audio_float * 32768).astype(np.int16)

        # Process in chunks
        total_duration = len(audio) / self.sample_rate
        self.results.duration = total_duration

        self.display.info(f"Processing {total_duration:.1f}s of audio...")

        for i in range(0, len(audio) - self.chunk_size, self.chunk_size):
            chunk = audio[i : i + self.chunk_size]
            timestamp = i / self.sample_rate

            self._process_chunk(chunk, timestamp)

        self.display.success("Processing complete")

    def _load_wav(self, audio_path: Path) -> Tuple[np.ndarray, int]:
        """Load a WAV file using the built-in wave module."""
        with wave.open(str(audio_path), "rb") as wf:
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            file_sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            audio_data = wf.readframes(n_frames)

        # Convert to numpy array
        if sample_width == 2:
            audio = np.frombuffer(audio_data, dtype=np.int16)
        elif sample_width == 4:
            audio = np.frombuffer(audio_data, dtype=np.int32)
            audio = (audio / 2147483648.0 * 32768).astype(np.int16)
        else:
            raise ValueError(f"Unsupported sample width: {sample_width}")

        # Convert stereo to mono if needed
        if n_channels == 2:
            audio = audio.reshape(-1, 2).mean(axis=1).astype(np.int16)

        return audio, file_sample_rate

    def _load_with_pydub(self, audio_path: Path) -> Tuple[np.ndarray, int]:
        """Load audio file using ffmpeg (supports MP3, OGG, FLAC, etc.).

        Uses ffmpeg directly via subprocess for maximum compatibility,
        especially with Python 3.14+ where audioop was removed.
        """
        import subprocess

        # Check if ffmpeg is available
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            raise RuntimeError(
                f"ffmpeg is required to load {audio_path.suffix} files. "
                f"Install with: sudo apt install ffmpeg (Linux) or brew install ffmpeg (macOS)"
            )

        self.display.info(f"Loading {audio_path.suffix} file with ffmpeg...")

        # Use ffmpeg to convert to raw PCM and pipe to stdout
        cmd = [
            "ffmpeg",
            "-i",
            str(audio_path),
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ac",
            "1",
            "-ar",
            str(self.sample_rate),
            "-loglevel",
            "error",
            "-",
        ]

        result = subprocess.run(cmd, capture_output=True)

        if result.returncode != 0:
            error_msg = result.stderr.decode() if result.stderr else "Unknown error"
            raise RuntimeError(f"ffmpeg failed: {error_msg}")

        # Convert raw bytes to numpy int16 array
        audio = np.frombuffer(result.stdout, dtype=np.int16)

        return audio, self.sample_rate

    def run_live(self, duration: float = 30.0):
        """Run live microphone detection test.

        Args:
            duration: How long to listen in seconds
        """
        try:
            import pyaudio
        except ImportError:
            self.display.error("pyaudio not installed. Run: pip install pyaudio")
            return

        self.display.separator()

        # Suppress ALSA error messages that spam the console
        from ctypes import CDLL

        def _alsa_error_handler(*args):
            """Dummy error handler to suppress ALSA warnings."""
            pass

        try:
            asound = CDLL("libasound.so.2")
            asound.snd_lib_error_set_handler(_alsa_error_handler)
        except OSError:
            pass  # libasound not available, skip suppression
        except Exception:
            pass  # If anything goes wrong, just continue without suppression

        pa = pyaudio.PyAudio()

        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size,
        )

        start_time = time.time()
        chunk_count = 0

        try:
            while True:
                # Only check duration if > 0 (0 means infinite)
                if duration > 0:
                    elapsed = time.time() - start_time
                    if elapsed >= duration:
                        break

                # Read audio chunk
                data = stream.read(self.chunk_size, exception_on_overflow=False)
                audio_chunk = np.frombuffer(data, dtype=np.int16)

                # Apply noise mixing (for testing robustness)
                if self.noise_level > 0:
                    audio_float = audio_chunk.astype(np.float32) / 32768.0
                    audio_float = self.mixer.mix_noise(
                        audio_float, noise_type=self.noise_type, level=self.noise_level
                    )
                    audio_chunk = (audio_float * 32768).astype(np.int16)

                timestamp = chunk_count * self.chunk_size / self.sample_rate
                self._process_chunk(audio_chunk, timestamp)

                chunk_count += 1

        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()
            self.results.duration = time.time() - start_time

    def _process_chunk(self, chunk: np.ndarray, timestamp: float):
        """Process a single audio chunk through the detection pipeline."""
        # DSP: Get spectral peaks
        peaks = self.dsp.process(chunk)

        # NEW: Filter peaks by frequency BEFORE generator
        # This removes irrelevant frequencies early in the pipeline
        filtered_peaks = self.freq_filter.filter_peaks(peaks)

        # Generator: Convert filtered peaks to events
        events = self.generator.process(filtered_peaks, timestamp)

        # Process each event through the matcher
        for event in events:
            if isinstance(event, ToneEvent):
                self.results.tone_events.append(event)
                # All tones are now relevant (pre-filtered), so display them
                self.display.tone_event(
                    event.timestamp,
                    event.frequency,
                    event.duration,
                )
                # Buffer event for windowed analysis
                self.matcher.add_event(event)

        # Evaluate windows periodically
        matches = self.matcher.evaluate(timestamp)

        for match in matches:
            self.results.detections.append(match)
            self.display.detection(
                match.profile_name,
                match.cycle_count,
                match.timestamp,
            )

    def show_results(self):
        """Display test results summary."""
        self.display.results_header()
        self.display.results_summary(
            detections=len(self.results.detections),
            duration=self.results.duration,
            profiles_tested=self.results.profiles_tested,
        )

        if self.results.detections:
            print("  Detections:")
            for d in self.results.detections:
                time_str = f"{int(d.timestamp // 60):02d}:{d.timestamp % 60:06.3f}"
                print(f"    • {time_str} - {d.profile_name}")
            print()
