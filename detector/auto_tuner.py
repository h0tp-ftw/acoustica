"""Compatibility facade for canonical acoustic-engine profile learning.

All DSP and pattern inference lives in ``acoustic_engine.learn``. New add-on
code should use :mod:`detector.profile_service`, which adds storage and
plain-language recording feedback without implementing a second detector.
"""

from acoustic_engine.learn import (
    extract_tone_events,
    infer_segments,
    learn_profile_from_audio,
    learn_profile_from_file,
)

from .profile_service import LearningResult, ProfileStore, RecordingMetrics

__all__ = [
    "LearningResult",
    "ProfileStore",
    "RecordingMetrics",
    "extract_tone_events",
    "infer_segments",
    "learn_profile_from_audio",
    "learn_profile_from_file",
]
