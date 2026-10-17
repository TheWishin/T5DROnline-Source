# T5DR lobby server. Standard-library Python only: nothing is pip-installed.
#
#   docker build -t t5lobby lobby/            (or: cd lobby && docker compose up -d --build)
#
# Pinned base: CPython 3.12.10 on Debian 12 slim (the version the test suite was run with).
# For fully reproducible builds pin the digest too: python:3.12.10-slim-bookworm@sha256:<digest>
# (`docker buildx imagetools inspect python:3.12.10-slim-bookworm` prints it).
FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    T5L_HOST=0.0.0.0 \
    T5L_DB=/data/t5lobby.db \
    T5L_BACKUP_DIR=/data/backups \
    T5L_STATUS_HOST=127.0.0.1 \
    T5L_STATUS_PORT=7780

# An unprivileged user with a fixed uid (match it when you chown a bind-mounted folder).
RUN groupadd --system --gid 10001 t5lobby \
 && useradd --system --uid 10001 --gid t5lobby --home-dir /data --shell /usr/sbin/nologin t5lobby \
 && mkdir -p /data /app \
 && chown t5lobby:t5lobby /data \
 && printf '#!/bin/sh\nexec python -m t5lobby.server.admin "$@"\n' > /usr/local/bin/t5lobby-admin \
 && chmod 755 /usr/local/bin/t5lobby-admin

WORKDIR /app
COPY t5lobby/ /app/t5lobby/
COPY servers.json run.py /app/
# Code is read-only for the service user.
RUN find /app -type d -exec chmod 755 {} + && find /app -type f -exec chmod 644 {} + \
 && python -c "import t5lobby.server.admin; from t5lobby.server import Config, LobbyServer; LobbyServer(Config(db=':memory:')).store.close()"

USER t5lobby
VOLUME ["/data"]
# TCP 7781: control channel (TLS when a certificate is mounted). UDP 7781: ping, registration,
# relay. UDP 7782: NAT type probe. 7780 (status) stays inside the container.
EXPOSE 7781/tcp 7781/udp 7782/udp

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-m", "t5lobby.server.admin", "health", "--quiet"]

STOPSIGNAL SIGTERM
CMD ["python", "-m", "t5lobby.server"]
