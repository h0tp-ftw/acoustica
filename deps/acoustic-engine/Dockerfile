# Base on Python 3.11 Slim (Debian Bookworm)
FROM python:3.11-slim-bookworm

# Prevent Python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies required for PyAudio and building Python packages
# portaudio19-dev is critical for PyAudio
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    portaudio19-dev \
    libasound2-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy configuration and dependency definitions first to utilize cache
COPY pyproject.toml README.md ./

# Install python dependencies (including dev dependencies for testing)
# We install with -e (editable) so changes in the mounted volume are reflected immediately if desired,
# but for a production build you usually wouldn't use -e. For "Quickstart" dev env, -e is perfect.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e ".[dev,audio,tuner]"

# Copy the rest of the application
COPY . .

# Default command runs the help to show available options
CMD ["python", "-m", "acoustic_engine.runner", "--help"]
