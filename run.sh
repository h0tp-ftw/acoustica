#!/bin/bash

# Log functions
log_info() { echo "[INFO] $(date +'%H:%M:%S') $1"; }
log_warn() { echo "[WARNING] $(date +'%H:%M:%S') $1"; }
log_error() { echo "[ERROR] $(date +'%H:%M:%S') $1"; }
log_debug() { [ "$DEBUG_MODE" = "true" ] && echo "[DEBUG] $(date +'%H:%M:%S') $1"; }

# Config Path
OPTIONS_JSON="/data/options.json"

# Helper to get config and handle "null"
get_config() {
    local val=$(jq -r "$1" $OPTIONS_JSON)
    if [ "$val" == "null" ] || [ -z "$val" ]; then
        echo ""
    else
        echo "$val"
    fi
}

# Load debug mode first
DEBUG_MODE=$(get_config '.debug_mode')
[ "$DEBUG_MODE" = "true" ] && log_info "Debug mode enabled"

# Auto-install custom integration (silent unless debug)
INTEGRATION_SOURCE="/app/custom_components/acoustic_alarm_detector"
INTEGRATION_DEST="/config/custom_components/acoustic_alarm_detector"

if [ -d "$INTEGRATION_SOURCE" ]; then
    mkdir -p /config/custom_components
    if cp -r "$INTEGRATION_SOURCE" "$INTEGRATION_DEST" 2>/dev/null; then
        log_info "Integration installed to /config/custom_components/"
    fi
fi

# Create ALSA configuration to route audio through PulseAudio
# Using /tmp since /usr/share/alsa is read-only in the container
ALSA_CFG_DIR="/tmp/alsa"
mkdir -p "$ALSA_CFG_DIR"
cat > "$ALSA_CFG_DIR/alsa.conf" << 'ALSAEOF'
pcm.!default {
    type pulse
}
ctl.!default {
    type pulse
}
ALSAEOF
export ALSA_CONFIG_PATH="$ALSA_CFG_DIR/alsa.conf"

# Audio Setup - Configure PulseAudio connection
if [ -S "/run/audio/pulse.sock" ]; then
    export PULSE_SERVER="unix:/run/audio/pulse.sock"
    export PULSE_RUNTIME_PATH="/run/audio"
    
    # Link cookie if provided
    if [ -f "/data/pulse-cookie" ]; then
        mkdir -p /root/.config/pulse
        ln -sf /data/pulse-cookie /root/.config/pulse/cookie
    fi
    
    # Debug: Show PulseAudio info  
    if [ "$DEBUG_MODE" = "true" ]; then
        log_debug "PulseAudio socket found"
        pactl info 2>/dev/null | head -5
        log_debug "Available audio sources:"
        pactl list sources short 2>/dev/null
    fi
    
    # Force unmute (silent)
    pactl set-source-mute @DEFAULT_SOURCE@ false &>/dev/null || true
    pactl set-source-volume @DEFAULT_SOURCE@ 100% &>/dev/null || true
else
    log_warn "PulseAudio socket NOT found - audio may not work"
fi

# Load configuration
export DEVICE_NAME=$(get_config '.device_name')
[ -z "$DEVICE_NAME" ] && export DEVICE_NAME="smoke_alarm_detector"

export ALARM_TYPE=$(get_config '.alarm_type')
[ -z "$ALARM_TYPE" ] && export ALARM_TYPE="smoke"

export TARGET_FREQ=$(get_config '.target_frequency')
export MIN_MAGNITUDE=$(get_config '.min_magnitude_threshold')
export BEEP_MIN=$(get_config '.beep_duration_min')
export BEEP_MAX=$(get_config '.beep_duration_max')
export PAUSE_MIN=$(get_config '.pause_duration_min')
export PAUSE_MAX=$(get_config '.pause_duration_max')
export CONFIRMATION_CYCLES=$(get_config '.confirmation_cycles')
export AUDIO_DEVICE_INDEX=$(get_config '.audio_device_index')
export FREQ_TOLERANCE=$(get_config '.frequency_tolerance')
export SAMPLE_RATE=44100

# Startup banner
log_info "Acoustic Listener v9.0.0"
log_info "Device: ${DEVICE_NAME} | Type: ${ALARM_TYPE} | Target: ${TARGET_FREQ}Hz"

# Debug info
if [ "$DEBUG_MODE" = "true" ]; then
    log_debug "Threshold: ${MIN_MAGNITUDE} | Pattern: ${BEEP_MIN}-${BEEP_MAX}s beep, ${PAUSE_MIN}-${PAUSE_MAX}s pause"
    log_debug "Confirmation cycles: ${CONFIRMATION_CYCLES}"
    log_debug "Contents of /app/detector:"
    ls -la /app/detector/ 2>/dev/null
    log_debug "Python version: $(python3 --version)"
fi

# Setup Python environment
cd /app
export PYTHONPATH=/app:$PYTHONPATH

# Validate detector package exists
if [ ! -d "/app/detector" ] || [ ! -f "/app/detector/__init__.py" ]; then
    log_error "Detector package not found - check Dockerfile"
    exit 1
fi

# Run the detector
log_info "Starting detector..."
cd /app/detector
exec python3 -u main.py
