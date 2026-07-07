# ALSA Configuration for USB Microphones on Raspberry Pi

## 1. List Available Audio Devices

```bash
# List all ALSA playback devices
aplay -L | grep sysdefault

# List all ALSA capture devices
arecord -L | grep sysdefault

# Identify USB audio devices specifically
arecord -L | grep -i usb

# Check sound card numbers
cat /proc/asound/cards
