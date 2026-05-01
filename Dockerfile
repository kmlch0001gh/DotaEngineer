FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD uvicorn dotaengineer.api.app:app --host 0.0.0.0 --port ${PORT:-8000}
