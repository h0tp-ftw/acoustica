#!/usr/bin/env bash
set -euo pipefail

OPTIONS_JSON="/data/options.json"

log_info() { echo "[INFO] $(date +'%H:%M:%S') $*"; }
log_warn() { echo "[WARNING] $(date +'%H:%M:%S') $*"; }
log_debug() {
    if [[ "${DEBUG_MODE:-false}" == "true" ]]; then
        echo "[DEBUG] $(date +'%H:%M:%S') $*"
    fi
}

get_option() {
    local selector="$1"
    if [[ ! -f "$OPTIONS_JSON" ]]; then
        return 0
    fi
    jq -r "${selector} // empty" "$OPTIONS_JSON"
}

export_option() {
    local selector="$1"
    local variable="$2"
    local value
    value="$(get_option "$selector")"
    if [[ -n "$value" ]]; then
        export "${variable}=${value}"
    fi
}

DEBUG_MODE="$(get_option '.debug_mode')"
DEBUG_MODE="${DEBUG_MODE:-false}"
export DEBUG_MODE

# Home Assistant exposes its audio server through this socket when audio: true.
if [[ -S "/run/audio/pulse.sock" ]]; then
    export PULSE_SERVER="unix:/run/audio/pulse.sock"
    export PULSE_RUNTIME_PATH="/run/audio"
    if [[ -f "/data/pulse-cookie" ]]; then
        export PULSE_COOKIE="/data/pulse-cookie"
    fi

    ALSA_CONFIG_PATH="/tmp/acoustic-alarm-alsa.conf"
    cat > "$ALSA_CONFIG_PATH" <<'EOF'
pcm.!default {
    type pulse
}
ctl.!default {
    type pulse
}
EOF
    export ALSA_CONFIG_PATH
    log_debug "Using Home Assistant PulseAudio socket"
else
    log_warn "Home Assistant audio socket was not found"
fi

export_option '.device_name' DEVICE_NAME
export_option '.alarm_type' ALARM_TYPE
export_option '.profile_id' PROFILE_ID
export_option '.audio_device_index' AUDIO_DEVICE_INDEX
export_option '.target_frequency' TARGET_FREQ
export_option '.frequency_tolerance' FREQ_TOLERANCE
export_option '.min_magnitude_threshold' MIN_MAGNITUDE
export_option '.confirmation_cycles' CONFIRMATION_CYCLES
export_option '.reset_timeout' RESET_TIMEOUT
export SAMPLE_RATE="${SAMPLE_RATE:-44100}"
export CHUNK_SIZE="${CHUNK_SIZE:-1024}"

log_info "Starting Acoustic Alarm Detector"
log_info "Device: ${DEVICE_NAME:-smoke_alarm_detector} | Category: ${ALARM_TYPE:-smoke} | Profile: ${PROFILE_ID:-preset}"

cd /app
python3 -c "import acoustic_engine; import detector.main" || {
    log_warn "Runtime dependency check failed"
    exit 1
}

exec python3 -u -m detector.main
