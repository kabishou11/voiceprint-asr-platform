FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY . /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv \
    && uv sync --extra asr-funasr --extra speaker-3ds

CMD ["uv", "run", "python", "-m", "apps.worker.app.worker"]
