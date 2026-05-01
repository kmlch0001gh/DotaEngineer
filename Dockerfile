FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir -e .

EXPOSE 7860

CMD uvicorn dotaengineer.api.app:app --host 0.0.0.0 --port ${PORT:-7860}
