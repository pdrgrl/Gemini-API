FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml and source code to install in editable mode with CLI extras
COPY pyproject.toml README.md LICENSE /app/
COPY src/ /app/src/

ENV SETUPTOOLS_SCM_PRETEND_VERSION=0.1.0
RUN pip install --no-cache-dir -e ".[cli]"

# Create directory structure for data persistence and auto-refreshed cookies
RUN mkdir -p /app/data /app/data/cookies ~/.local/state/gemini

ENV PYTHONUNBUFFERED=1
ENV GEMINI_COOKIE_PATH=/app/data/cookies

ENTRYPOINT ["gemini"]
CMD []
