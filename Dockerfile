FROM python:3.15-slim@sha256:2da676046630d7bf14c6764ae1143dc7fa0377a53f94bf5a642f0b214aca5bce

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    PYTHON_DOTENV_DISABLED=1 \
    STORAGE_BACKEND=firestore \
    DATA_DIR=/var/lib/fundo-centenario

WORKDIR /app

# Temporary Debian security pin; remove once the pinned base includes deb13u3 or newer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpcre2-8-0=10.46-1~deb13u3 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
COPY backend/requirements.lock backend/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r backend/requirements.lock \
    && python -m pip uninstall -y pip

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

# The HTTP port is set by Cloud Run. exec preserves signal delivery to Uvicorn.
CMD ["sh", "-c", "exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-access-log"]
