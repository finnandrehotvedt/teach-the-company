FROM python:3.13.7-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system --gid 10001 app \
    && adduser --system --uid 10001 --ingroup app --home /app app

COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --requirement /tmp/requirements.txt

COPY --chown=app:app src/ /app/
COPY --chown=app:app scripts/entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh \
    && mkdir -p /app/staticfiles \
    && mkdir -p /app/private-data \
    && mkdir -p /run/fetch-proxy \
    && chown -R app:app /app/staticfiles /app/private-data /run/fetch-proxy

USER app

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "2", "--timeout", "30", "--access-logfile", "-", "--error-logfile", "-"]
