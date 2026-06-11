FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV TZ=America/New_York

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tzdata curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN mkdir -p /app/logs /app/results \
    && chmod +x /app/bot_status.py || true

CMD ["python", "main.py"]
