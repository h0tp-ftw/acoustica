FROM ghcr.io/home-assistant/base:3.22

WORKDIR /app

RUN apk add --no-cache \
        alsa-lib \
        alsa-plugins-pulse \
        bash \
        jq \
        libffi \
        portaudio \
        python3 \
        py3-pip \
    && apk add --no-cache --virtual .build-dependencies \
        gcc \
        libffi-dev \
        musl-dev \
        python3-dev

COPY requirements.txt ./
RUN python3 -m pip install \
        --break-system-packages \
        --no-cache-dir \
        --prefer-binary \
        -r requirements.txt \
    && apk del .build-dependencies

COPY detector/ ./detector/
COPY tuner/index.html tuner/styles.css tuner/audio-engine.js tuner/app.js ./tuner/
COPY run.sh ./run.sh
RUN chmod a+x /app/run.sh

LABEL \
    io.hass.name="Acoustic Alarm Detector" \
    io.hass.description="Local acoustic smoke and CO alarm detection" \
    io.hass.version="9.5.0" \
    io.hass.type="app" \
    io.hass.arch="aarch64|amd64"

CMD ["/app/run.sh"]
