"""Constants for the Acoustic Alarm Detector integration."""

DOMAIN = "acoustic_alarm_detector"

PLATFORMS = ["binary_sensor"]

# Event fired by the add-on (see detector/ha_bridge.py EVENT_TYPE) carrying
# {"name": str, "state": bool, "device_class": str}.
EVENT_TYPE = "acoustic_alarm_detector_event"

# Discovery file the add-on writes: {"profiles": [{"name", "device_class"}, ...]}.
PROFILES_PATH = "/config/acoustic_alarm_detector/profiles.json"

# All detectors are grouped under a single Home Assistant device.
DEVICE_ID = "acoustic_alarm_detector"
DEVICE_NAME = "Acoustic Alarm Detector"
MANUFACTURER = "h0tp / acoustic-engine"

DEFAULT_DEVICE_CLASS = "sound"
