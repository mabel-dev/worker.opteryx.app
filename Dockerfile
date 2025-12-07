FROM python:3.13-slim

# Create a non-root user 'norris'
RUN useradd --create-home norris
WORKDIR /home/norris

# Install build deps
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project metadata and code that setuptools needs to build the editable package.
# NOTE: These files must be in the build context before running `uv sync`.
COPY pyproject.toml ./pyproject.toml
COPY README.md ./README.md
COPY app ./app
# install uv tool and run `uv sync` to install project dependencies from pyproject.toml
RUN pip install --no-cache-dir uv && \
    uv sync || (echo "uv sync failed; ensure pyproject.toml is present and valid in the build context" && exit 1)
RUN chown -R norris:norris /home/norris
USER norris

ENV PATH=/home/norris/.venv/bin:$PATH
ENV PORT=8080
EXPOSE 8080

CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT --limit-max-requests 2048
