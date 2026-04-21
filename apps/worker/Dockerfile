FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY . /app

RUN pip install uv && uv sync

CMD ["uv", "run", "python", "-m", "apps.worker.app.main"]
