# Imagen unica de web, worker y admin-usuarios (CLAUDE.md: "la misma imagen").
# Base fijada por digest (RS-18). Dependencias con hash desde uv.lock:
#   uv export --frozen --no-dev --no-emit-project --format requirements-txt -o requirements.lock
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock

COPY pyproject.toml manage.py ./
COPY src ./src
RUN pip install --no-deps . \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin jml \
    && install -d -o jml -m 0700 /var/lib/jml/soportes

# collectstatic necesita importar los ajustes, que leen secretos: se usan valores de un solo uso
# que no quedan en la imagen (el directorio se borra en la misma capa).
RUN install -d /tmp/s \
    && python -c "import secrets; print(secrets.token_urlsafe(50))" > /tmp/s/django_secret_key \
    && echo x > /tmp/s/db_password \
    && JML_SECRETOS_DIR=/tmp/s python manage.py collectstatic --noinput -v 0 \
    && rm -rf /tmp/s

USER jml
EXPOSE 8000
# Un solo proceso con hilos: los desafios TOTP a medio camino viven en su memoria (S-29).
CMD ["gunicorn", "config.wsgi", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "8", \
     "--timeout", "60", "--max-requests", "2000", "--max-requests-jitter", "200"]
