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
# PortAudio (sounddevice / PyAudio) needs a working default device; point the
# default PCM/CTL at the pulse plugin. Prefer a system-wide /etc/asound.conf, but
# this container's rootfs is read-only (only /data, /config, /tmp are writable),
# so fall back to a config in /tmp and point alsa-lib at it via ALSA_CONFIG_PATH.
# ALSA_CONFIG_PATH replaces the default search, so include the system alsa.conf
# first to keep the 'pulse' plugin type (from alsa-plugins) defined.
ASOUND_OVERRIDE='pcm.!default { type pulse }
ctl.!default { type pulse }'

if printf '%s\n' "$ASOUND_OVERRIDE" > /etc/asound.conf 2>/dev/null; then
    [ "$DEBUG_MODE" = "true" ] && log_info "Routed ALSA default -> PulseAudio via /etc/asound.conf"
else
    SYS_ALSA="/usr/share/alsa/alsa.conf"
    ALSA_ALT="/tmp/asound.conf"
    {
        [ -r "$SYS_ALSA" ] && echo "<$SYS_ALSA>"
        printf '%s\n' "$ASOUND_OVERRIDE"
    } > "$ALSA_ALT"
    export ALSA_CONFIG_PATH="$ALSA_ALT"
    log_warn "/etc read-only — routed ALSA via ALSA_CONFIG_PATH=$ALSA_ALT."
    [ -r "$SYS_ALSA" ] || log_warn "  $SYS_ALSA unreadable — 'type pulse' may be undefined (check AppArmor)."
fi

if [ -S "/run/audio/pulse.sock" ]; then
    export PULSE_SERVER="unix:/run/audio/pulse.sock"
    export PULSE_RUNTIME_PATH="/run/audio"

    # Point the client at the cookie via env — don't write /root (read-only rootfs).
    [ -f "/data/pulse-cookie" ] && export PULSE_COOKIE="/data/pulse-cookie"

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

# Pre-flight: the 'detector' package must import. If it doesn't, the image is
# incomplete (interrupted build / out-of-space overlay) — dump enough to tell
# why, instead of a bare ModuleNotFoundError.
if ! python3 -c "import detector" 2>/dev/null; then
    log_error "Cannot import the 'detector' package from /app — the image looks incomplete."
    log_error "Contents of /app:"
    ls -la /app 2>&1 | while IFS= read -r line; do log_error "  $line"; done
    log_error "PYTHONPATH=$PYTHONPATH"
    log_error "sys.path=$(python3 -c 'import sys; print(sys.path)' 2>&1)"
    log_error "Fix: uninstall + reinstall the add-on to force a clean rebuild, and check host disk space."
    exit 1
fi

log_info "Starting Acoustic Alarm Detector..."
exec python3 -u -m detector.main
