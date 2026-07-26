"""Acoustica add-on.

A thin bridge around the standalone `acoustic_engine` library:

- config:    read Home Assistant add-on options -> list of AlarmProfiles
- ha_bridge: turn engine detections into Home Assistant binary_sensor states
- main:      wire profiles + audio into a ParallelEngine and run it

All audio capture, DSP, and pattern matching live in `acoustic_engine`; this
package only adapts it to the Home Assistant add-on environment.
"""

__version__ = "10.4.0"
