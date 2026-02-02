"""Audio mixer for noise injection during testing."""

from typing import Literal

import numpy as np

NoiseType = Literal["white", "pink", "brown"]


class AudioMixer:
    """Mixes noise with audio for specificity testing."""

    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate
        self._pink_state = None

    def mix_noise(
        self,
        audio: np.ndarray,
        noise_type: NoiseType = "white",
        level: float = 0.1,
    ) -> np.ndarray:
        """Mix noise into audio signal.

        Args:
            audio: Input audio samples (float32, normalized)
            noise_type: Type of noise ('white', 'pink', 'brown')
            level: Noise level 0.0-1.0

        Returns:
            Mixed audio with noise added
        """
        if level <= 0:
            return audio

        noise = self._generate_noise(len(audio), noise_type)

        # Scale noise by level
        noise = noise * level

        # Mix with original audio
        mixed = audio * (1 - level * 0.3) + noise

        # Clip to prevent overflow
        mixed = np.clip(mixed, -1.0, 1.0)

        return mixed.astype(np.float32)

    def _generate_noise(self, length: int, noise_type: NoiseType) -> np.ndarray:
        """Generate noise of specified type."""
        if noise_type == "white":
            return self._white_noise(length)
        elif noise_type == "pink":
            return self._pink_noise(length)
        elif noise_type == "brown":
            return self._brown_noise(length)
        else:
            return self._white_noise(length)

    def _white_noise(self, length: int) -> np.ndarray:
        """Generate white noise (uniform frequency distribution)."""
        return np.random.uniform(-1, 1, length).astype(np.float32)

    def _pink_noise(self, length: int) -> np.ndarray:
        """Generate pink noise (1/f spectrum).

        Uses Voss-McCartney algorithm for efficient pink noise.
        """
        # Number of octaves
        num_rows = 16

        # Initialize state if needed
        if self._pink_state is None or len(self._pink_state) != num_rows:
            self._pink_state = np.random.uniform(-1, 1, num_rows)

        output = np.zeros(length, dtype=np.float32)

        for i in range(length):
            # Determine which row to update based on trailing zeros
            row = 0
            n = i
            while n > 0 and (n & 1) == 0:
                row += 1
                n >>= 1
                if row >= num_rows:
                    break

            if row < num_rows:
                self._pink_state[row] = np.random.uniform(-1, 1)

            output[i] = np.sum(self._pink_state) / num_rows

        # Normalize
        max_val = np.max(np.abs(output))
        if max_val > 0:
            output = output / max_val

        return output

    def _brown_noise(self, length: int) -> np.ndarray:
        """Generate brown/red noise (1/f^2 spectrum).

        Created by integrating white noise.
        """
        white = self._white_noise(length)
        brown = np.cumsum(white)

        # Normalize to [-1, 1]
        max_val = np.max(np.abs(brown))
        if max_val > 0:
            brown = brown / max_val

        return brown.astype(np.float32)

    def add_random_bursts(
        self,
        audio: np.ndarray,
        frequency: float = 0.5,
        duration_range: tuple = (0.1, 0.5),
        level: float = 0.3,
    ) -> np.ndarray:
        """Add random noise bursts to audio.

        Args:
            audio: Input audio samples
            frequency: Average bursts per second
            duration_range: (min, max) burst duration in seconds
            level: Burst noise level

        Returns:
            Audio with random bursts added
        """
        if frequency <= 0 or level <= 0:
            return audio

        result = audio.copy()
        duration_sec = len(audio) / self.sample_rate

        # Number of bursts follows Poisson distribution
        num_bursts = np.random.poisson(frequency * duration_sec)

        for _ in range(num_bursts):
            # Random start position
            start_sec = np.random.uniform(0, duration_sec)
            start_sample = int(start_sec * self.sample_rate)

            # Random duration
            burst_duration = np.random.uniform(*duration_range)
            burst_samples = int(burst_duration * self.sample_rate)

            if start_sample + burst_samples > len(audio):
                burst_samples = len(audio) - start_sample

            if burst_samples > 0:
                # Generate burst with envelope
                burst = self._white_noise(burst_samples) * level

                # Apply fade in/out envelope
                fade_samples = min(int(0.01 * self.sample_rate), burst_samples // 4)
                if fade_samples > 0:
                    burst[:fade_samples] *= np.linspace(0, 1, fade_samples)
                    burst[-fade_samples:] *= np.linspace(1, 0, fade_samples)

                result[start_sample : start_sample + burst_samples] += burst

        return np.clip(result, -1.0, 1.0).astype(np.float32)
