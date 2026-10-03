#!/usr/bin/env python3
"""Create a local, mode-0600 Compose environment without printing secrets."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / ".env"


def main() -> None:
    if TARGET.exists():
        content = TARGET.read_text(encoding="utf-8")
        existing = {line.split("=", 1)[0] for line in content.splitlines() if "=" in line}
        additions = {
            "COMPOSE_PROJECT_NAME": "teach_the_company",
            "TTC_HTTP_PORT": "18574",
            "TTC_BACKEND_SUBNET": "172.31.111.0/28",
            "TTC_FETCH_EGRESS_SUBNET": "172.31.110.0/28",
            "DJANGO_ADMIN_USERNAME": "admin",
            "DJANGO_ADMIN_EMAIL": "admin@example.invalid",
            "DJANGO_ADMIN_PASSWORD": secrets.token_urlsafe(36),
            "TTC_OPEN_SIGNUP": "true",
            "TTC_PRIVATE_DATA_ROOT": "/app/private-data",
            "TTC_AGENT_BACKEND": "evidence",
            "TTC_AGENT_API_URL": "",
            "TTC_AGENT_MODEL": "local-model",
            "TTC_AGENT_API_KEY": "",
            "TTC_AGENT_TIMEOUT_SECONDS": "30",
            "TTC_SECURITY_LAB_PORT": "18575",
            "TTC_SECURITY_LAB_INTERNAL_SUBNET": "172.31.112.0/29",
            "TTC_SECURITY_LAB_PREVIEW_SUBNET": "172.31.113.0/29",
        }
        missing = {key: value for key, value in additions.items() if key not in existing}
        if missing:
            replacement = TARGET.with_suffix(".tmp")
            descriptor = os.open(replacement, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                if content and not content.endswith("\n"):
                    handle.write("\n")
                for key, value in missing.items():
                    handle.write(f"{key}={value}\n")
            os.replace(replacement, TARGET)
            os.chmod(TARGET, 0o600)
            print(f"Added missing protected settings to: {TARGET}")
            return
        print(f"Environment already exists: {TARGET}")
        return

    values = {
        "COMPOSE_PROJECT_NAME": "teach_the_company",
        "TTC_HTTP_PORT": "18574",
        "TTC_BACKEND_SUBNET": "172.31.111.0/28",
        "TTC_FETCH_EGRESS_SUBNET": "172.31.110.0/28",
        "POSTGRES_DB": "teach_the_company",
        "POSTGRES_USER": "teach_the_company",
        "POSTGRES_PASSWORD": secrets.token_urlsafe(36),
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
        "DJANGO_DEBUG": "false",
        "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "",
        "DJANGO_SITE_ORIGIN": "http://127.0.0.1:18574",
        "DJANGO_SECURE_COOKIES": "false",
        "DJANGO_SECURE_SSL_REDIRECT": "false",
        "DJANGO_SECURE_HSTS_SECONDS": "0",
        "DJANGO_TRUST_PROXY_HEADERS": "false",
        "DJANGO_TRUSTED_PROXY_IPS": "",
        "DJANGO_ADMIN_USERNAME": "admin",
        "DJANGO_ADMIN_EMAIL": "admin@example.invalid",
        "DJANGO_ADMIN_PASSWORD": secrets.token_urlsafe(36),
        "BOOTSTRAP_DEMO": "true",
        "TTC_OPEN_SIGNUP": "true",
        "TTC_PRIVATE_DATA_ROOT": "/app/private-data",
        "TTC_AGENT_BACKEND": "evidence",
        "TTC_AGENT_API_URL": "",
        "TTC_AGENT_MODEL": "local-model",
        "TTC_AGENT_API_KEY": "",
        "TTC_AGENT_TIMEOUT_SECONDS": "30",
        "TTC_SECURITY_LAB_PORT": "18575",
        "TTC_SECURITY_LAB_INTERNAL_SUBNET": "172.31.112.0/29",
        "TTC_SECURITY_LAB_PREVIEW_SUBNET": "172.31.113.0/29",
    }
    content = "".join(f"{key}={value}\n" for key, value in values.items())
    descriptor = os.open(TARGET, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(content)
    print(f"Created protected local environment: {TARGET}")


if __name__ == "__main__":
    main()
