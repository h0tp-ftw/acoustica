# 🎙 Input Module

The `input` module handles the low-level details of audio capture and hardware interfacing. It abstractions the raw audio stream into a clean, callback-based interface.

## 🛠 Components

### `AudioListener`

The primary component of this module. It manages the lifecycle of an audio stream using **PyAudio**.

- **Threaded Capture**: Captures audio in a dedicated background thread to prevent processing jitter from causing audio dropouts.
- **Hardware Agnostic**: Supports selecting specific device indices or using the system default.
- **Robustness**: Uses `exception_on_overflow=False` to handle transient system load spikes gracefully without crashing.

## 📋 usage

```python
from acoustic_engine.input.listener import AudioListener
from acoustic_engine.config import AudioSettings

def my_callback(audio_chunk):
    # audio_chunk is a numpy array of int16 samples
    print(f"Captured {len(audio_chunk)} samples")

settings = AudioSettings(sample_rate=44100, chunk_size=1024)
listener = AudioListener(settings, on_audio_chunk=my_callback)

if listener.setup():
    listener.start() # This blocks while running
```

## ⚙️ Key Features

- **Format**: Captures 16-bit PCM Mono audio at the configured sample rate.
- **Validation**: Automatically validates device capabilities during setup.
- **Diagnostics**: Includes `_list_devices()` for troubleshooting audio hardware paths and indices.

## 🔌 Decoupling

While the `Engine` uses `AudioListener` for live capture, the two are fully decoupled. You can pass audio chunks to the engine from any source (files, network) using `engine.process_chunk()`, bypassing this module entirely if needed.
