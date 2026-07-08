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

# --- Audio: ALSA default -> PulseAudio -------------------------------------- #
# HA injects a (read-only) /etc/asound.conf that routes ALSA's default to pulse
# and exposes the server at /run/audio/pulse.sock. The AppArmor profile MUST
# grant read on /etc/asound.conf, or ALSA discards its ENTIRE config and every
# audio backend dies at Pa_Initialize (that was the whole audio saga — see
# apparmor.txt). As a belt-and-suspenders for hosts that don't inject it, also
# drop a ~/.asoundrc in writable /tmp (HOME points there).
export HOME=/tmp
printf 'pcm.!default { type pulse }\n' > /tmp/.asoundrc 2>/dev/null

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

# --- Tuner web UI (HA Ingress) --------------------------------------------- #
# Serve the acoustic-engine tuner + profile API behind Ingress, in the
# background alongside the detector. Best-effort: if it fails, detection still
# runs. Profiles saved from the UI land in /config/.../profiles, where the
# detector reads them.
TUNER_PROFILES_DIR="/config/acoustic_alarm_detector/profiles"
mkdir -p "$TUNER_PROFILES_DIR"
# Launch via `python3 -m`, not the `acoustic-engine` console script: AppArmor
# grants exec on /usr/bin but the interpreter must *read* a console script
# (needs 'r'); the module form reads from site-packages, which is already
# allowed — so this works regardless.
if python3 -c "import acoustic_engine.tuner.validate" >/dev/null 2>&1; then
    python3 -m acoustic_engine.tuner.validate --host 0.0.0.0 --port 8099 \
        --profiles-dir "$TUNER_PROFILES_DIR" &
    log_info "Tuner UI on ingress port 8099 — open the add-on's sidebar panel."
else
    log_warn "Tuner server unavailable (engine + fastapi/uvicorn not importable)."
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

if [ "$DEBUG_MODE" = "true" ]; then
    log_info "Starting Acoustic Alarm Detector (debug: container stays alive on exit)..."
    python3 -u -m detector.main
    rc=$?
    log_warn "detector exited (rc=$rc). DEBUG mode: keeping the container alive so you can"
    log_warn "  docker exec -it addon_581b527c_acoustic_alarm_detector bash"
    log_warn "and run audio diagnostics in the real environment. Stop the add-on to end."
    exec tail -f /dev/null
else
    log_info "Starting Acoustic Alarm Detector..."
    exec python3 -u -m detector.main
fi
