FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY douyin_to_social_media/requirements.txt /tmp/dts-requirements.txt
RUN pip install --no-cache-dir -r /tmp/dts-requirements.txt

COPY shopeetool /app/shopeetool
COPY douyin_to_social_media/*.py /app/douyin_to_social_media/
COPY douyin_to_social_media/publishers /app/douyin_to_social_media/publishers
COPY douyin_to_social_media/web /app/douyin_to_social_media/web

ENV PYTHONUNBUFFERED=1 \
    DTS_HOST=0.0.0.0 \
    DTS_PORT=8766 \
    OLLAMA_URL=http://127.0.0.1:11434/api/generate

WORKDIR /app/douyin_to_social_media
CMD ["python", "-u", "admin_web.py"]
