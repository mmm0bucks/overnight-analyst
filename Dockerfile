FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /bin/uv

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_COMPILE_BYTECODE=1 PATH=/opt/venv/bin:$PATH

# dependencies first: this layer is cached until uv.lock changes
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src src
RUN uv sync --locked --no-dev
COPY demo demo

# default: free offline demo; override the command for real runs (see README)
CMD ["sh", "-c", "overnight init-demo && overnight run --today 2026-10-27"]
