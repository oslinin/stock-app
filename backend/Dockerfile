FROM python:3.12-slim

WORKDIR /srv/backend

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

EXPOSE 8000

# --loop asyncio keeps ib_async, APScheduler and FastAPI on one plain asyncio loop
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "asyncio"]
