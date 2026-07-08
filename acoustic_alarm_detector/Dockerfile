# Home Assistant add-on image.
ARG BUILD_FROM
FROM $BUILD_FROM

# System dependencies:
# - git: install the pinned engine from its git repo
# - portaudio(-dev): PortAudio runtime + headers for sounddevice / PyAudio
# - alsa-* / pulseaudio-utils: route the add-on's audio to HA's PulseAudio
# - gcc/g++/musl-dev/python3-dev/libffi-dev: build any wheels not prebuilt (cffi, PyAudio)
# - bash/jq/curl: startup script helpers
RUN apk add --no-cache \
    python3 \
    py3-pip \
    python3-dev \
    git \
    alsa-lib \
    alsa-utils \
    alsa-plugins-pulse \
    portaudio \
    portaudio-dev \
    libffi-dev \
    gcc \
    g++ \
    musl-dev \
    pulseaudio-utils \
    bash \
    curl \
    jq

WORKDIR /app

# Make `python3 -m detector.main` resolve regardless of cwd or Python safe-path.
ENV PYTHONPATH=/app

# Install the detection engine (+ PyAudio fallback backend) and its deps.
# --prefer-binary uses musllinux wheels for numpy/cffi instead of building them.
COPY requirements.txt .
RUN python3 -m pip install --break-system-packages --no-cache-dir --prefer-binary \
        -r requirements.txt

# Application code
COPY detector/ ./detector/
COPY run.sh .
RUN chmod a+x ./run.sh

# Custom integration (auto-installed into /config by run.sh)
COPY custom_components/ ./custom_components/

# NOTE: ALSA -> PulseAudio routing is set up at runtime in run.sh via
# /etc/asound.conf (additive), so the stock alsa.conf + alsa-plugins definitions
# that make `type pulse` work stay intact.

LABEL \
    io.hass.name="Acoustic Alarm Detector" \
    io.hass.description="Listen on a microphone and detect alarms/beeps as Home Assistant binary sensors" \
    io.hass.version="10.1.0" \
    io.hass.type="addon" \
    io.hass.arch="aarch64|amd64|armhf|armv7"

ENTRYPOINT ["/bin/bash", "/app/run.sh"]
