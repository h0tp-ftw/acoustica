"""Compatibility imports for the single acoustic-engine audio listener.

Production code imports these classes directly from ``acoustic_engine``. This
module contains no audio implementation of its own.
"""

from acoustic_engine.config import AudioSettings
from acoustic_engine.input.listener import AudioListener

AudioConfig = AudioSettings

__all__ = ["AudioConfig", "AudioListener", "AudioSettings"]
