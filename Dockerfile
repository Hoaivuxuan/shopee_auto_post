FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir requests playwright \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*
COPY shopeetool /app/shopeetool
COPY api_shopee /app/api_shopee

ENV ADMIN_HOST=0.0.0.0
ENV ADMIN_PORT=8765
ENV PYTHONUNBUFFERED=1

EXPOSE 8765
CMD ["python", "-m", "shopeetool.admin_web"]
