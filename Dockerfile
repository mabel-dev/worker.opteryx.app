# Stage 1: Builder
FROM python:3.13-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy only the files needed for dependency installation
COPY pyproject.toml ./

# Create a virtual environment and install dependencies
RUN uv venv /opt/venv
RUN uv pip install --no-cache --python /opt/venv/bin/python -r pyproject.toml

# Create a small entrypoint script to handle the PORT environment variable
# since distroless has no shell to expand it.
RUN echo 'import os, sys, uvicorn; \
sys.path.append("/app"); \
port = int(os.environ.get("PORT", 8080)); \
uvicorn.run("app.main:application", host="0.0.0.0", port=port)' > /app/entrypoint.py

# Stage 2: Final (Distroless)
# We use the 'cc' variant because it includes glibc, which Python and pyarrow need.
FROM gcr.io/distroless/cc-debian12

# Copy Python runtime from the builder
COPY --from=builder /usr/local/lib/python3.13 /usr/local/lib/python3.13
COPY --from=builder /usr/local/bin/python3.13 /usr/local/bin/python3.13
COPY --from=builder /usr/local/bin/python3 /usr/local/bin/python3

# Copy the virtual environment
COPY --from=builder /opt/venv /opt/venv

# Copy required shared libraries (libgomp is required by pyarrow)
COPY --from=builder /usr/lib/x86_64-linux-gnu/libgomp.so.1 /usr/lib/x86_64-linux-gnu/libgomp.so.1

# Copy app and entrypoint
WORKDIR /app
COPY app ./app
COPY --from=builder /app/entrypoint.py ./entrypoint.py

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1
EXPOSE 8080

# Use the nonroot user provided by distroless (UID 65532)
USER 65532

# Start the application using the entrypoint script
ENTRYPOINT ["/usr/local/bin/python3", "/app/entrypoint.py"]
