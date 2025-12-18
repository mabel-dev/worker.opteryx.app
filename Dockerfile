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

# Copy only the files needed for dependency installation
COPY pyproject.toml ./

# Install dependencies into a virtual environment
RUN uv venv /opt/venv && \
    VIRTUAL_ENV=/opt/venv uv pip install -r pyproject.toml

# Stage 2: Final
FROM python:3.13-slim

# Create a non-root user 'norris'
RUN useradd --create-home norris
WORKDIR /home/norris

# Copy the virtual environment from the builder
COPY --from=builder /opt/venv /opt/venv

# Copy service code
COPY app ./app
RUN chown -R norris:norris /home/norris

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH"
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
EXPOSE 8080

USER norris

CMD ["uvicorn", "app.main:application", "--host", "0.0.0.0", "--port", "8080"]
