"""Removed legacy analyzer.

Spectral analysis is provided exclusively by ``acoustic_engine``. This file is
kept temporarily so older local imports fail by missing symbols rather than
silently selecting a second DSP implementation.
"""

__all__: tuple[str, ...] = ()
