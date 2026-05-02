FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:${PATH}"

COPY pyproject.toml uv.lock README.md /app/

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv \
    && uv sync --extra asr-funasr --extra speaker-3ds --no-install-project \
    && uv pip install --python .venv/bin/python \
        torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 \
        --index-url https://download.pytorch.org/whl/cu124

COPY . /app

RUN uv sync --extra asr-funasr --extra speaker-3ds --inexact

EXPOSE 8000

CMD [".venv/bin/python", "-m", "uvicorn", "apps.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
