FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    ENABLE_MOCK_PSP=false \
    DATA_DIR=/var/lib/fundo-centenario

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

RUN groupadd --gid 10001 fundo \
    && useradd --uid 10001 --gid fundo --no-create-home fundo \
    && mkdir -p /var/lib/fundo-centenario \
    && chown fundo:fundo /var/lib/fundo-centenario \
    && chmod 700 /var/lib/fundo-centenario

COPY backend/__init__.py backend/__init__.py
COPY backend/app/ backend/app/
COPY backend/templates/ backend/templates/
COPY frontend/ frontend/

USER 10001:10001
EXPOSE 8000

# A persistência JSONL atual exige um único processo.
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
