#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

for path in Dockerfile config.yaml requirements.txt run.sh apparmor.txt detector/main.py custom_components/acoustic_alarm_detector/runtime.py; do
    [[ -e "$path" ]] || fail "Missing required file: $path"
done

grep -q '^FROM ghcr.io/home-assistant/base:' Dockerfile \
    || fail "Dockerfile must use an explicit Home Assistant base image"
grep -q '^acoustic-engine==1\.4\.0$' requirements.txt \
    || fail "acoustic-engine must remain pinned to 1.4.0"
grep -q 'python3 -u -m detector\.main' run.sh \
    || fail "run.sh must use the canonical package entry point"
grep -q '^ingress: true$' config.yaml \
    || fail "The guided profile UI must remain available through ingress"
grep -q '^ingress_port: 8099$' config.yaml \
    || fail "The ingress port must match the profile server"
grep -q 'COPY tuner/index.html tuner/styles.css tuner/audio-engine.js tuner/app.js ./tuner/' Dockerfile \
    || fail "Dockerfile must include the guided UI assets"
grep -q "export_option '.profile_id' PROFILE_ID" run.sh \
    || fail "run.sh must export the selected canonical profile ID"
grep -q "export_option '.audio_device_index' AUDIO_DEVICE_INDEX" run.sh \
    || fail "run.sh must export the selected microphone"
grep -q '^  audio_device_index: -1$' config.yaml \
    || fail "The default microphone must remain schema-backed"
grep -q '"/api/audio/select"' detector/profile_server.py \
    || fail "Ingress must expose the single microphone-selection path"
grep -q '"/api/profiles/.*activate"\|/activate' detector/profile_server.py \
    || fail "Ingress must expose hot profile activation"

if grep -q 'custom_components' run.sh; then
    fail "The add-on must not auto-copy the Home Assistant integration"
fi
if grep -q 'set-source-volume' run.sh; then
    fail "The add-on must not change global microphone volume"
fi
if grep -R -Eq 'getUserMedia|estimateFrequency|zero.cross|AudioContext|MediaRecorder' tuner/index.html tuner/audio-engine.js tuner/app.js; then
    fail "The ingress UI must use the add-on microphone and real engine, not browser DSP"
fi

if grep -Eq '^  - (armhf|armv7)$' config.yaml; then
    fail "Unsupported 32-bit architectures are still declared"
fi
if grep -Eq '^(map:|hassio_api:)' config.yaml; then
    fail "Broad Home Assistant/Supervisor access must not be reintroduced"
fi
if grep -R -q '/states/' detector; then
    fail "The add-on must not write Home Assistant entity states directly"
fi
if grep -R -q 'websocket' custom_components/acoustic_alarm_detector --include='*.py'; then
    fail "The integration must not register a second WebSocket state path"
fi
if grep -qE '/(config|homeassistant)/\*\*' apparmor.txt; then
    fail "AppArmor must not grant broad Home Assistant configuration access"
fi
if ! grep -q '^homeassistant_api: true$' config.yaml; then
    fail "The add-on must enable the Home Assistant Core API proxy"
fi
if ! grep -A1 '^discovery:' config.yaml | grep -q 'acoustic_alarm_detector'; then
    fail "The add-on must declare its Supervisor discovery service"
fi
if ! grep -q '"/discovery"' detector/integration_client.py; then
    fail "Integration pairing must use the limited Supervisor discovery endpoint"
fi
if grep -Eq '^map:|config:rw|homeassistant:rw' config.yaml; then
    fail "The add-on must not map the Home Assistant configuration directory"
fi
if grep -R -q '/states/' detector custom_components --include='*.py'; then
    fail "Entity state must be owned by the integration, not written through /states"
fi
if grep -R -q 'websocket' custom_components/acoustic_alarm_detector --include='*.py'; then
    fail "The integration must use the single event protocol, not a second WebSocket path"
fi
if grep -Eq '/(config|homeassistant)/' apparmor.txt; then
    fail "AppArmor must not grant access to Home Assistant configuration files"
fi

if [[ -n "${PYTHON_BIN:-}" ]]; then
    read -r -a PYTHON_CMD <<< "$PYTHON_BIN"
elif command -v py >/dev/null 2>&1 && py -3.12 -c "import sys" >/dev/null 2>&1; then
    PYTHON_CMD=(py -3.12 -X utf8)
elif command -v python3 >/dev/null 2>&1 && python3 -c "import sys" >/dev/null 2>&1; then
    PYTHON_CMD=(python3)
elif command -v python >/dev/null 2>&1 && python -c "import sys" >/dev/null 2>&1; then
    PYTHON_CMD=(python)
else
    fail "A working Python interpreter is required"
fi

"${PYTHON_CMD[@]}" -m compileall -q detector tests custom_components
"${PYTHON_CMD[@]}" -c '
import json
from pathlib import Path
import yaml

yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
json.loads(Path("custom_components/acoustic_alarm_detector/manifest.json").read_text(encoding="utf-8"))
'
"${PYTHON_CMD[@]}" -m pytest

if command -v node >/dev/null 2>&1; then
    node --check tuner/audio-engine.js
    node --check tuner/app.js
fi

if command -v docker >/dev/null 2>&1; then
    docker build --pull -t local/acoustic-alarm-detector:validation .
else
    echo "WARNING: Docker is unavailable; container build was not executed." >&2
fi

echo "Validation complete."
