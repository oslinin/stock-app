FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /srv/worker

COPY pyproject.toml uv.lock ./
COPY worker.py ./
# --locked: fail the build rather than silently drift from uv.lock
RUN uv sync --locked --no-editable

CMD ["uv", "run", "--no-sync", "python", "worker.py"]
