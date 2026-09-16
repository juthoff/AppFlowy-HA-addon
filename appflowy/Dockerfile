# syntax=docker/dockerfile:1
#
# Home Assistant Add-on: AppFlowy (fully self-contained, last AGPL-3.0 release)
#
# This packages the last AppFlowy-Cloud release published before the project
# was relicensed to a commercial license (AppFlowy-IO/AppFlowy-Cloud, git tag
# 0.9.64, released 2025-07-04, AGPL-3.0). appflowy_cloud / admin_frontend /
# appflowy_worker are pulled from the exact, immutable Docker Hub digests of
# that release (never touched since; verified via the Docker Hub API before
# writing this file). gotrue and AppFlowy Web are rebuilt from source at the
# matching upstream refs, because that is what the 0.9.64 docker-compose.yml
# itself does. See NOTICE.md for the exact source of every component.
ARG TARGETARCH

# ---------------------------------------------------------------------------
# gotrue (AppFlowy's fork of Supabase Auth) - built from source, MIT license
# ---------------------------------------------------------------------------
FROM golang:1.22-alpine AS gotrue-builder
ARG GOTRUE_REF="0.8.0"
RUN apk add --no-cache git
WORKDIR /go/src/supabase/auth
# gotrue hardcodes the `Secure` flag on its session cookies (internal/api/token.go,
# setCookieToken/clearCookieToken) with no config knob to disable it. This add-on never
# terminates TLS itself, so any browser that isn't on "localhost" (e.g. any other device
# on the LAN, reached via the host IP over plain HTTP) silently drops the cookie, breaking
# login. A non-Secure cookie works fine over both HTTP and a user's own HTTPS-terminating
# reverse proxy, so it's safe to disable unconditionally.
RUN git clone --depth 1 --branch ${GOTRUE_REF} https://github.com/AppFlowy-IO/auth.git . \
    && sed -i 's/Secure:   true,/Secure:   false,/' internal/api/token.go \
    && CGO_ENABLED=0 go build -o /out/auth .
RUN cp -r /go/src/supabase/auth/migrations /out/migrations

# ---------------------------------------------------------------------------
# AppFlowy Web - built from source (static SPA), AGPL-3.0
# ---------------------------------------------------------------------------
FROM node:20.12.0 AS web-builder
ARG APPFLOWY_WEB_REF="v0.1.18"
WORKDIR /app
RUN npm install -g pnpm@8.5.0 \
    && git clone --depth 1 --branch ${APPFLOWY_WEB_REF} https://github.com/AppFlowy-IO/AppFlowy-Web.git . \
    && sed -i 's|https://test.appflowy.cloud||g' src/components/main/app.hooks.ts \
    && pnpm install --frozen-lockfile \
    && pnpm run build

# ---------------------------------------------------------------------------
# appflowy_cloud / admin_frontend / appflowy_worker: pinned upstream images
# (exact digests of the appflowyinc/* images pushed together with the 0.9.64
# release on 2025-07-04, i.e. before the relicense; Docker Hub confirms none
# of these tags/digests were touched since)
# ---------------------------------------------------------------------------
FROM appflowyinc/appflowy_cloud@sha256:ded3da3a25fe7a76c28108adb9849b8aa0ce02b0da5898bc7dd58a09c00e5139 AS appflowy_cloud_amd64
FROM appflowyinc/appflowy_cloud@sha256:0b0f11031b6787579148e3138f152485c12f8aba1c228cb5bbccde1a521e16d2 AS appflowy_cloud_arm64
FROM appflowy_cloud_${TARGETARCH} AS appflowy_cloud_src

FROM appflowyinc/admin_frontend@sha256:443d92faa034b002a1c71e6692245f7a3dcc352f55e4c6dcfdd4b1aa53eaf063 AS admin_frontend_amd64
FROM appflowyinc/admin_frontend@sha256:1e79dcf3efe6425228fef075afd7a11e344189da43e5a958d670fa01513d6f99 AS admin_frontend_arm64
FROM admin_frontend_${TARGETARCH} AS admin_frontend_src

FROM appflowyinc/appflowy_worker@sha256:e9bcb9f712b2fb75318674fa874c0ef460d7b3b7487c99560f2b5ce5564991d2 AS appflowy_worker_amd64
FROM appflowyinc/appflowy_worker@sha256:7986e875e4fc825c73de0bad7a58f464ae81019c6c6bdb2c3c0c5790df69b4f5 AS appflowy_worker_arm64
FROM appflowy_worker_${TARGETARCH} AS appflowy_worker_src

# ---------------------------------------------------------------------------
# MinIO server binary - copied from the official multi-arch image.
# dl.min.io's plain binary downloads (the previously used
# https://dl.min.io/server/minio/release/<arch>/minio URLs) were shut down
# by MinIO (HTTP 410 Gone) after this add-on was first written; MinIO's own
# Docker Hub org was also removed. quay.io/minio/minio is MinIO's official,
# actively maintained multi-arch image and is the documented replacement.
# ---------------------------------------------------------------------------
FROM quay.io/minio/minio:latest AS minio_src

# ---------------------------------------------------------------------------
# Final runtime image
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim AS runtime
ARG TARGETARCH
ENV DEBIAN_FRONTEND=noninteractive \
    S6_KEEP_ENV=1 \
    S6_CMD_WAIT_FOR_SERVICES_TIMEOUT=0

# --- base packages, s6-overlay, nginx, redis, postgresql 16 + pgvector ----
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg xz-utils jq openssl \
        nginx redis-server \
        postgresql-common; \
    /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y; \
    apt-get update; \
    apt-get install -y --no-install-recommends postgresql-16 postgresql-16-pgvector; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "${TARGETARCH}" in \
        amd64) S6ARCH=x86_64 ;; \
        arm64) S6ARCH=aarch64 ;; \
        *) echo "unsupported arch ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    S6_VERSION=3.2.3.2; \
    curl -fsSL -o /tmp/s6-noarch.tar.xz "https://github.com/just-containers/s6-overlay/releases/download/v${S6_VERSION}/s6-overlay-noarch.tar.xz"; \
    curl -fsSL -o /tmp/s6-arch.tar.xz "https://github.com/just-containers/s6-overlay/releases/download/v${S6_VERSION}/s6-overlay-${S6ARCH}.tar.xz"; \
    tar -C / -Jxpf /tmp/s6-noarch.tar.xz; \
    tar -C / -Jxpf /tmp/s6-arch.tar.xz; \
    rm -f /tmp/s6-noarch.tar.xz /tmp/s6-arch.tar.xz

COPY --from=minio_src /usr/bin/minio /usr/local/bin/minio

# --- dedicated low-privilege user for the AppFlowy application services ---
RUN useradd --system --create-home --home-dir /opt/appflowy --shell /usr/sbin/nologin appflowy

# --- gotrue (static binary + its migrations, side by side) ---------------
RUN mkdir -p /opt/appflowy/gotrue
COPY --from=gotrue-builder /out/auth /opt/appflowy/gotrue/auth
COPY --from=gotrue-builder /out/migrations /opt/appflowy/gotrue/migrations

# --- AppFlowy Web static build, served directly by nginx ------------------
RUN mkdir -p /opt/appflowy/web
COPY --from=web-builder /app/dist /opt/appflowy/web

# --- vendor the exact runtime libs of each pinned Rust binary, so they -----
# --- keep working regardless of this image's own glibc/openssl version ----
RUN mkdir -p \
    /opt/appflowy/vendor/appflowy_cloud/bin /opt/appflowy/vendor/appflowy_cloud/lib \
    /opt/appflowy/vendor/admin_frontend/bin /opt/appflowy/vendor/admin_frontend/lib \
    /opt/appflowy/vendor/appflowy_worker/bin /opt/appflowy/vendor/appflowy_worker/lib

COPY --from=appflowy_cloud_src /usr/local/bin/appflowy_cloud /opt/appflowy/vendor/appflowy_cloud/bin/appflowy_cloud
COPY --from=appflowy_cloud_src /lib/ /opt/appflowy/vendor/appflowy_cloud/lib/lib/
COPY --from=appflowy_cloud_src /usr/lib/ /opt/appflowy/vendor/appflowy_cloud/lib/usr-lib/
COPY --from=appflowy_cloud_src /etc/ssl/certs/ /opt/appflowy/vendor/appflowy_cloud/lib/ssl-certs/

COPY --from=admin_frontend_src /usr/local/bin/admin_frontend /opt/appflowy/vendor/admin_frontend/bin/admin_frontend
COPY --from=admin_frontend_src /app/assets/ /opt/appflowy/vendor/admin_frontend/assets/
COPY --from=admin_frontend_src /lib/ /opt/appflowy/vendor/admin_frontend/lib/lib/
COPY --from=admin_frontend_src /usr/lib/ /opt/appflowy/vendor/admin_frontend/lib/usr-lib/

COPY --from=appflowy_worker_src /usr/local/bin/appflowy_worker /opt/appflowy/vendor/appflowy_worker/bin/appflowy_worker
COPY --from=appflowy_worker_src /lib/ /opt/appflowy/vendor/appflowy_worker/lib/lib/
COPY --from=appflowy_worker_src /usr/lib/ /opt/appflowy/vendor/appflowy_worker/lib/usr-lib/
COPY --from=appflowy_worker_src /etc/ssl/certs/ /opt/appflowy/vendor/appflowy_worker/lib/ssl-certs/

# --- runtime filesystem layout, permissions --------------------------------
RUN set -eux; \
    mkdir -p /data/postgres /data/minio /data/redis /run/postgresql; \
    chown -R postgres:postgres /data/postgres /run/postgresql; \
    chown -R redis:redis /data/redis; \
    chown -R appflowy:appflowy /opt/appflowy /data/minio; \
    rm -f /etc/nginx/sites-enabled/default

COPY rootfs/ /

# `COPY <dir>/ /` carries over the *exact* permission bits of the source
# directories on the build host. If rootfs/ (or any parent) was ever checked
# out/extracted with a restrictive umask (e.g. 700), this COPY silently
# clobbers /etc's mode from 755 down to 700, locking every non-root service
# (postgres, redis, gotrue, ...) out of /etc entirely - breaking NSS lookups
# and config file access in a very confusing way. Re-assert sane permissions
# explicitly here instead of trusting the host state.
RUN set -eux; \
    chmod 755 /etc /etc/cont-init.d /etc/services.d /etc/nginx; \
    find /etc/services.d -mindepth 1 -maxdepth 1 -type d -exec chmod 755 {} \; ; \
    chmod +x /etc/cont-init.d/*.sh /etc/services.d/*/run

ENTRYPOINT ["/init"]
