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

# --- Audio: route ALSA's default *capture* PCM through PulseAudio ----------- #
# PortAudio (sounddevice / PyAudio) needs a working default device. Override ONLY
# pcm.!default -> pulse; do NOT touch ctl.!default. PortAudio enumerates sound
# cards via the CTL interface during Pa_Initialize, and pointing ctl at the pulse
# plugin makes that enumeration fail here ("error getting host API"), so leave
# ctl as the stock hw-based default (which initializes fine).
# Delivery is a DROP-IN, same mechanism as /etc/asound.conf. The rootfs is
# read-only (only /data, /config, /tmp writable), so on read-only /etc we point
# HOME at a writable dir and drop the override in ~/.asoundrc /
# ~/.config/alsa/asoundrc, which the stock alsa.conf loads via the same hook —
# keeping the system config (and its plugin defs) intact.
ASOUND_OVERRIDE='pcm.!default { type pulse }'

if printf '%s\n' "$ASOUND_OVERRIDE" > /etc/asound.conf 2>/dev/null; then
    [ "$DEBUG_MODE" = "true" ] && log_info "Routed ALSA default -> PulseAudio via /etc/asound.conf"
else
    export HOME=/tmp
    mkdir -p /tmp/.config/alsa 2>/dev/null
    printf '%s\n' "$ASOUND_OVERRIDE" > /tmp/.asoundrc
    printf '%s\n' "$ASOUND_OVERRIDE" > /tmp/.config/alsa/asoundrc 2>/dev/null
    log_warn "/etc read-only — routed ALSA via ~/.asoundrc (HOME=/tmp)."
fi

if [ -S "/run/audio/pulse.sock" ]; then
    export PULSE_SERVER="unix:/run/audio/pulse.sock"
    export PULSE_RUNTIME_PATH="/run/audio"

    # Point the client at the cookie via env — don't write /root (read-only rootfs).
    [ -f "/data/pulse-cookie" ] && export PULSE_COOKIE="/data/pulse-cookie"

    # Always list capture sources — this is how we tell whether a mic exists.
    PA_SOURCES="$(pactl list sources short 2>/dev/null)"
    if [ -n "$PA_SOURCES" ]; then
        log_info "PulseAudio sources (capture devices):"
        printf '%s\n' "$PA_SOURCES" | while IFS= read -r src; do log_info "  $src"; done
    else
        log_warn "No PulseAudio sources — no microphone is available to the host."
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
