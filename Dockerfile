# Use Home Assistant base image
ARG BUILD_FROM
FROM $BUILD_FROM

# Install system dependencies
# We use apk for the base libraries and pip for the python packages
RUN apk add --no-cache \
    python3 \
    py3-pip \
    python3-dev \
    alsa-lib \
    alsa-utils \
    alsa-plugins-pulse \
    portaudio \
    portaudio-dev \
    gcc \
    g++ \
    musl-dev \
    linux-headers \
    pulseaudio-utils \
    bash \
    curl \
    iproute2 \
    jq



WORKDIR /app

# Install Python requirements
# Note: Installing numpy/scipy via pip on Alpine can be slow,
# but it's the only way to ensure they land in the correct Python environment
COPY requirements.txt .
COPY deps/ ./deps/

RUN python3 -m pip install --break-system-packages --no-cache-dir --prefer-binary numpy==1.26.4 websockets==12.0
RUN python3 -m pip install --break-system-packages --no-cache-dir --prefer-binary pyaudio==0.2.14
# Scipy is the heaviest, we try to install it last
RUN python3 -m pip install --break-system-packages --no-cache-dir --prefer-binary scipy==1.12.0

# Install acoustic-engine (bundled dependency)
RUN python3 -m pip install --break-system-packages --no-cache-dir ./deps/acoustic-engine

# Copy application code
COPY detector/ ./detector/
COPY run.sh .
RUN chmod a+x ./run.sh

# Copy custom integration (for auto-install)
COPY custom_components/ ./custom_components/

# Labels for Home Assistant
LABEL \
    io.hass.name="Acoustic Alarm Detector" \
    io.hass.description="Acoustic smoke and CO alarm detection with native integration" \
    io.hass.version="9.0.0" \
    io.hass.type="addon" \
    io.hass.arch="aarch64|amd64|armhf|armv7"

# Create ALSA configuration to route audio to PulseAudio
# Using printf for better portability
RUN mkdir -p /usr/share/alsa && \
    printf 'pcm.!default {\n  type pulse\n}\nctl.!default {\n  type pulse\n}\n' > /usr/share/alsa/alsa.conf

ENTRYPOINT ["/bin/bash", "/app/run.sh"]

