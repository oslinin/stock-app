FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /srv/backend

COPY pyproject.toml uv.lock ./
COPY app ./app
# --locked: fail the build rather than silently drift from uv.lock
RUN uv sync --locked --no-dev --no-editable

EXPOSE 8000

# --loop asyncio keeps ib_async, APScheduler and FastAPI on one plain asyncio loop
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "asyncio"]
