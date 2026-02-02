"""Digital Signal Processing (DSP) layer for audio analysis."""

import logging
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Peak:
    """A spectral peak detected in FFT analysis."""

    frequency: float
    magnitude: float
    bin_index: int


class SpectralMonitor:
    """Monitors audio chunks for spectral peaks.

    Performs windowed FFT analysis to identify significant frequency peaks
    that might correspond to alarm tones.
    """

    def __init__(
        self,
        sample_rate: int,
        chunk_size: int,
        min_magnitude: float = 0.05,
        min_sharpness: float = 1.5,
        noise_floor_factor: float = 3.0,
        max_peaks: int = 5,
        noise_learning_rate: float = 0.01,
    ):
        """Initialize the spectral monitor.

        Args:
            sample_rate: Audio sample rate in Hz
            chunk_size: Number of samples per chunk
            min_magnitude: Minimum magnitude to consider a peak
            min_sharpness: Peak required to be X times higher than neighbors
            noise_floor_factor: Multiplier for adaptive noise floor threshold
            max_peaks: Maximum number of peaks to return
            noise_learning_rate: Alpha for noise profile updates (0.0 to 1.0)
        """
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.freq_bins = np.fft.rfftfreq(chunk_size, 1.0 / sample_rate)
        self.window = np.hanning(chunk_size)
        self.noise_profile: Optional[np.ndarray] = None

        # Configuration
        self.min_magnitude = min_magnitude
        self.min_sharpness = min_sharpness
        self.noise_floor_factor = noise_floor_factor
        self.max_peaks = max_peaks
        self.noise_learning_rate = noise_learning_rate

    def _update_noise_profile(self, fft_data: np.ndarray):
        """Update the background noise profile using asymmetric EMA."""
        if self.noise_profile is None:
            self.noise_profile = fft_data.copy()
            return

        # Asymmetric update:
        # - FAST update if current energy < background (we found a quieter floor)
        # - SLOW update if current energy > background (potential signal or increased noise)

        # We can implement this vector-wise
        # Define alpha for each bin
        # If fft < profile: alpha = 0.1 (fast adaptation to quiet)
        # If fft > profile: alpha = self.noise_learning_rate (slow adaptation to noise)

        # Vectorized implementation:
        is_quieter = fft_data < self.noise_profile
        alpha = np.where(is_quieter, 0.1, self.noise_learning_rate)

        self.noise_profile = (1 - alpha) * self.noise_profile + alpha * fft_data

    def process(self, audio_chunk: np.ndarray) -> List[Peak]:
        """Process an audio chunk and return significant spectral peaks.

        Args:
            audio_chunk: Raw audio samples (int16)

        Returns:
            List of Peak objects sorted by magnitude (descending)
        """
        # Handle partial chunks
        if len(audio_chunk) != self.chunk_size:
            return []

        # Normalize and window
        float_chunk = audio_chunk.astype(np.float32)  # Windowing
        windowed = float_chunk * self.window

        # FFT
        fft_data = np.abs(np.fft.rfft(windowed))

        if len(fft_data) == 0:
            return []

        # Update noise profile
        self._update_noise_profile(fft_data)

        # -- Spectral Subtraction / Adaptive Thresholding --
        # We use ADDITIVE thresholding because high volume stationary noise (like a fan)
        # does not necessarily have high variance.
        # Threshold = Mean + Margin.
        # We use (min_magnitude * noise_floor_factor) as the safety margin.
        safety_margin = self.min_magnitude * self.noise_floor_factor
        dynamic_thresholds = np.maximum(self.min_magnitude, self.noise_profile + safety_margin)

        max_val = np.max(fft_data)
        # Quick check: if the loudest peak isn't above its local threshold, bail early
        # (This is approximate since max(fft) might not be at the same bin as max(threshold),
        # but if max(fft) < min(thresholds), we are definitely silent)
        if max_val < np.min(dynamic_thresholds):
            return []

        # Peak finding
        peaks: List[Peak] = []

        # Skip DC and Nyquist edge bins
        for i in range(2, len(fft_data) - 2):
            mag = fft_data[i]

            # Check against per-bin threshold
            if mag < dynamic_thresholds[i]:
                continue

            # Check if local peak
            if mag > fft_data[i - 1] and mag > fft_data[i + 1]:
                # Sharpness check
                neighbors = (
                    fft_data[i - 2] + fft_data[i - 1] + fft_data[i + 1] + fft_data[i + 2]
                ) / 4.0
                if neighbors == 0:
                    neighbors = 1e-6

                if mag / neighbors > self.min_sharpness:
                    # -- Parabolic Interpolation --
                    # Use neighbors to find the "true" fractional peak center
                    # Formula: peak + 0.5 * (left - right) / (left - 2*center + right)
                    alpha = fft_data[i - 1]
                    beta = fft_data[i]
                    gamma = fft_data[i + 1]

                    denom = alpha - 2 * beta + gamma
                    if denom == 0:
                        delta = 0.0
                    else:
                        delta = 0.5 * (alpha - gamma) / denom

                    # Calculate precise frequency
                    true_bin = i + delta
                    freq = true_bin * (self.sample_rate / self.chunk_size)

                    peaks.append(Peak(frequency=freq, magnitude=mag, bin_index=i))

        # Sort by magnitude descending, limit to top peaks
        peaks.sort(key=lambda x: x.magnitude, reverse=True)
        return peaks[: self.max_peaks]
