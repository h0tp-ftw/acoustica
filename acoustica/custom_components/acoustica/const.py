"""Constants for the Acoustica integration."""

DOMAIN = "acoustica"

PLATFORMS = ["binary_sensor"]

# Event fired by the add-on (see detector/ha_bridge.py EVENT_TYPE) carrying
# {"name": str, "state": bool, "device_class": str}.
EVENT_TYPE = "acoustica_event"

# Discovery file the add-on writes: {"profiles": [{"name", "device_class"}, ...]}.
PROFILES_PATH = "/config/acoustica/profiles.json"

# All detectors are grouped under a single Home Assistant device.
DEVICE_ID = "acoustica"
DEVICE_NAME = "Acoustica"
MANUFACTURER = "h0tp / acoustic-engine"

DEFAULT_DEVICE_CLASS = "sound"
