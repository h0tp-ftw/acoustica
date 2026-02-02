import logging
import sys
from pathlib import Path

import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from acoustic_engine.processing.dsp import SpectralMonitor

logging.basicConfig(level=logging.DEBUG)


def test_dsp():
    sample_rate = 44100
    chunk_size = 1024
    min_mag = 2.5

    print(f"Testing DSP with N={chunk_size}, Mag={min_mag}")

    monitor = SpectralMonitor(sample_rate=sample_rate, chunk_size=chunk_size, min_magnitude=min_mag)

    # Generate 1000 Hz sine wave
    t = np.linspace(0, chunk_size / sample_rate, chunk_size, False)
    # Amplitude 0.1 (-20dB)
    # RFFT mag should be ~ 0.1 * 512 = 51.2
    sine = 0.1 * np.sin(2 * np.pi * 1000 * t).astype(np.float32)

    # Process
    peaks = monitor.process(sine)

    print(f"Found {len(peaks)} peaks")
    for p in peaks:
        print(f"  Peak: {p.frequency:.2f} Hz, Mag: {p.magnitude:.2f}")

    if len(peaks) > 0:
        print("✅ DSP Success")
    else:
        print("❌ DSP Failed")


if __name__ == "__main__":
    test_dsp()
