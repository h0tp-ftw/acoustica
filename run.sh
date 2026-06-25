#!/bin/bash
# Acoustic Alarm Detector add-on startup.
# Sets up audio (ALSA -> PulseAudio), installs the companion custom integration
# into /config, then runs the detector. All detection options are read from
# /data/options.json by the Python app itself.

log_info()  { echo "[INFO]  $(date +'%H:%M:%S') $1"; }
log_warn()  { echo "[WARN]  $(date +'%H:%M:%S') $1"; }
log_error() { echo "[ERROR] $(date +'%H:%M:%S') $1"; }

OPTIONS_JSON="/data/options.json"
DEBUG_MODE="$(jq -r '.debug // false' "$OPTIONS_JSON" 2>/dev/null)"
[ "$DEBUG_MODE" = "true" ] && log_info "Debug mode enabled"

# --- Install / update the companion custom integration -------------------- #
# Gives Home Assistant the binary_sensor entities. Requires one HA Core restart
# after the first install before the integration can be added.
INTEGRATION_SRC="/app/custom_components/acoustic_alarm_detector"
INTEGRATION_DST="/config/custom_components/acoustic_alarm_detector"
if [ -d "$INTEGRATION_SRC" ]; then
    mkdir -p /config/custom_components
    if cp -r "$INTEGRATION_SRC" "/config/custom_components/" 2>/dev/null; then
        log_info "Custom integration installed/updated at $INTEGRATION_DST"
        log_info "If this is the first install, restart Home Assistant Core once, then add"
        log_info "the 'Acoustic Alarm Detector' integration under Settings -> Devices & Services."
    else
        log_warn "Could not copy the custom integration into /config/custom_components"
    fi
fi

# --- Audio: route ALSA's default device through PulseAudio ----------------- #
# Point the default PCM/CTL at the pulse plugin via a system-wide asound.conf.
# This is ADDITIVE to the stock ALSA config (which defines the pulse plugin via
# alsa-plugins) — replacing alsa.conf instead would drop those definitions and
# break capture.
cat > /etc/asound.conf << 'ALSAEOF'
pcm.!default {
    type pulse
}
ctl.!default {
    type pulse
}
ALSAEOF

if [ -S "/run/audio/pulse.sock" ]; then
    export PULSE_SERVER="unix:/run/audio/pulse.sock"
    export PULSE_RUNTIME_PATH="/run/audio"

    if [ -f "/data/pulse-cookie" ]; then
        mkdir -p /root/.config/pulse
        ln -sf /data/pulse-cookie /root/.config/pulse/cookie
    fi

    if [ "$DEBUG_MODE" = "true" ]; then
        log_info "PulseAudio socket found. Sources:"
        pactl list sources short 2>/dev/null || true
    fi

    # Make sure the default mic isn't muted / is at full gain.
    pactl set-source-mute @DEFAULT_SOURCE@ false &>/dev/null || true
    pactl set-source-volume @DEFAULT_SOURCE@ 100% &>/dev/null || true
else
    log_warn "PulseAudio socket not found at /run/audio/pulse.sock — the mic may be unavailable."
    log_warn "Confirm 'audio: true' for the add-on and that a microphone is attached."
fi

# --- Run the detector ------------------------------------------------------ #
cd /app || exit 1
export PYTHONPATH=/app:$PYTHONPATH

if [ ! -f "/app/detector/main.py" ]; then
    log_error "Detector code not found at /app/detector — check the image build."
    exit 1
fi

log_info "Starting Acoustic Alarm Detector..."
exec python3 -u -m detector.main
