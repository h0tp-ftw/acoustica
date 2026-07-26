#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

for path in \
    Dockerfile \
    config.yaml \
    CHANGELOG.md \
    DOCS.md \
    requirements.txt \
    constraints.txt \
    requirements-dev.txt \
    run.sh \
    detector/main.py \
    detector/integration_client.py \
    detector/tuner_server.py \
    tuner/acoustica-controls.js \
    tests/browser/easy_setup_harness.html \
    tests/browser/easy_setup_harness.js \
    custom_components/acoustica/manifest.json; do
    [[ -e "$path" ]] || fail "Missing required file: $path"
done

grep -q '^discovery:' config.yaml \
    || fail "Supervisor discovery must remain declared"
grep -q 'python3 -m detector.tuner_server' run.sh \
    || fail "run.sh must start the Acoustica tuner wrapper"
grep -q 'TUNER_PROFILES_DIR="/data/profiles"' run.sh \
    || fail "New profiles must remain in add-on-owned storage"
grep -q 'COPY tuner/ ./tuner/' Dockerfile \
    || fail "The image must package the injected tuner assets"
grep -q 'EVENT_STATE_UPDATE = "acoustica_state"' detector/integration_client.py \
    || fail "The versioned integration event changed unexpectedly"
grep -q '/api/acoustica/detectors/disable' detector/tuner_server.py \
    || fail "Detector disable controls must remain exposed through ingress"

if grep -Eq '(^|[[:space:]])[^#[:space:]]+(>=|~=|>)' requirements.txt constraints.txt; then
    fail "Runtime dependencies must remain exactly pinned"
fi

if grep -R -Eq 'getUserMedia|MediaRecorder|AudioContext' tuner; then
    fail "Acoustica controls must not open the browser microphone"
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

"${PYTHON_CMD[@]}" -m compileall -q detector custom_components tests
"${PYTHON_CMD[@]}" -c '
import json
from pathlib import Path
import yaml

yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
json.loads(Path("custom_components/acoustica/manifest.json").read_text(encoding="utf-8"))
'
"${PYTHON_CMD[@]}" -m pytest -q

if command -v node >/dev/null 2>&1; then
    node --check tuner/acoustica-controls.js
    node --check tests/browser/easy_setup_harness.js
fi

if [[ "${RUN_DOCKER_BUILD:-0}" == "1" ]]; then
    command -v docker >/dev/null 2>&1 || fail "Docker was requested but is unavailable"
    docker build --pull \
        --build-arg "BUILD_FROM=${BUILD_FROM:-ghcr.io/home-assistant/amd64-base:3.21}" \
        -t local/acoustica:validation .
else
    echo "Docker build is handled by the dedicated multi-architecture CI job."
fi

echo "Validation complete."
