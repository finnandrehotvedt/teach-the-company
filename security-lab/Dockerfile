FROM python:3.13.7-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system --gid 10002 lab \
    && adduser --system --uid 10002 --ingroup lab --home /app lab

COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --requirement /tmp/requirements.txt

COPY --chown=lab:lab app/ /app/
RUN mkdir -p /var/lib/security-lab/backups \
    && mkdir -p /var/lib/security-lab-socket \
    && chown -R lab:lab /var/lib/security-lab /var/lib/security-lab-socket

USER lab

EXPOSE 8000

CMD ["gunicorn", "security_lab.application:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2", "--timeout", "20", "--access-logfile", "-", "--error-logfile", "-"]
