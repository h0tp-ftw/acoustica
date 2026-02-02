# 🌊 Processing Module (DSP)

The `processing` module transforms raw time-domain audio data into filtered spectral information. It is responsible for identifying where the energy is in the sound spectrum and filtering out the noise.

## 🛠 Components

### `SpectralMonitor` (in `dsp.py`)

Performs the core Digital Signal Processing required to detect tones.

- **Windowed FFT**: Applies a Hanning window to reduce spectral leakage before performing a Real FFT.
- **Adaptive Noise Floor**: Calculates a dynamic threshold based on the median energy of the spectrum.
- **Per-Bin Noise Profiling**: Background noise is learned per-frequency-bin (Spectral Subtraction). This allows the system to ignore loud, stationary noises (like fans, freezers, or motors) while still detecting quiet alarms in other frequency bands.
- **Parabolic Interpolation**: Uses mathematical interpolation between FFT bins to find the "true" frequency of a peak with sub-bin precision.
- **Sharpness Check**: Ensures identified peaks are actually distinct tones and not just wide-band noise.

### `FrequencyFilter` (in `filter.py`)

The engine's first line of defense against false positives.

- **Relevance Screening**: Discards any spectral peaks that fall outside the frequency ranges defined in your `AlarmProfile`s.
- **Performance Optimization**: By discarding irrelevant data early, it prevents the more complex `EventGenerator` and `Matcher` from wasting CPU cycles on speech, music, or rumble.
- **Dynamic Merging**: Automatically merges overlapping or adjacent frequency ranges for high-speed lookups.

## 📋 Usage

```python
from acoustic_engine.processing.dsp import SpectralMonitor
from acoustic_engine.processing.filter import FrequencyFilter

# Setup DSP
monitor = SpectralMonitor(sample_rate=44100, chunk_size=1024)

# Setup Filter for a 3kHz alarm
screener = FrequencyFilter()
screener.add_range(2900, 3100)

# Process a chunk
peaks = monitor.process(audio_chunk)
relevant_peaks = screener.filter_peaks(peaks)

for peak in relevant_peaks:
    print(f"Found {peak.frequency:.1f}Hz at magnitude {peak.magnitude:.2f}")
```

## ⚙️ Design Philosophy

The processing layer is designed to be "deaf" to everything except the target sounds. The combination of **spectral subtraction** and **frequency screening** makes this engine exceptionally stable in real-world environments like kitchens, factories, and warehouses.
