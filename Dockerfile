FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY entrypoint.sh ./
RUN chmod +x /app/entrypoint.sh

COPY healthcheck.sh ./
RUN chmod +x /app/healthcheck.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
  CMD /app/healthcheck.sh || exit 1

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
