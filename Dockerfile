# Stage 1: Builder
FROM python:3.13-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml ./

# Create a virtual environment and install dependencies
RUN uv venv /opt/venv
RUN uv pip install --no-cache --python /opt/venv/bin/python -r pyproject.toml

# Stage 2: Final
# We use the same base image as the builder to ensure GLIBC compatibility
FROM python:3.13-slim

# Install runtime dependencies (libgomp1 is required by pyarrow)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user 'norris'
RUN useradd --create-home --shell /bin/bash norris
WORKDIR /home/norris

# Copy the virtual environment from the builder
COPY --from=builder /opt/venv /opt/venv

# Copy service code
COPY app ./app

# Ensure the non-root user owns the app and the venv
RUN chown -R norris:norris /home/norris /opt/venv

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH"
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/home/norris"
EXPOSE 8080

USER norris

# Use the shell form of CMD to allow $PORT expansion from the environment
# We use 'python -m uvicorn' to ensure we use the venv's interpreter
CMD exec python -m uvicorn app.main:service --host 0.0.0.0 --port ${PORT:-8080}
