#!/bin/bash
# Reads the Home Assistant add-on options and renders /etc/appflowy/env,
# a single shell-sourceable file that every service's run script loads.
set -euo pipefail

OPTIONS_FILE="/data/options.json"
SECRETS_FILE="/data/secrets.env"
ENV_FILE="/etc/appflowy/env"
mkdir -p /etc/appflowy

opt() { jq -r ".$1 // \"\"" "$OPTIONS_FILE"; }
opt_bool() { jq -r "(.$1 // false)" "$OPTIONS_FILE"; }

# --- secrets are generated once and persisted across restarts/updates -----
if [ ! -f "$SECRETS_FILE" ]; then
    echo "[appflowy] first start: generating secrets in ${SECRETS_FILE}"
    {
        echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)"
        echo "GOTRUE_JWT_SECRET=$(openssl rand -hex 32)"
        echo "MINIO_ACCESS_KEY=appflowy"
        echo "MINIO_SECRET_KEY=$(openssl rand -hex 24)"
    } > "$SECRETS_FILE"
    chmod 600 "$SECRETS_FILE"
fi
# shellcheck disable=SC1090
source "$SECRETS_FILE"

FQDN="$(opt fqdn)"
SCHEME="$(opt scheme)"
[ -z "$SCHEME" ] && SCHEME="http"
if [ -z "$FQDN" ]; then
    BASE_URL="${SCHEME}://localhost:8099"
else
    BASE_URL="${SCHEME}://${FQDN}"
fi

ADMIN_EMAIL="$(opt admin_email)"
ADMIN_PASSWORD="$(opt admin_password)"
if [ -z "$ADMIN_PASSWORD" ]; then
    echo "[appflowy] WARNING: no admin_password set in the add-on configuration." >&2
    echo "[appflowy]          Set one and restart the add-on before using it." >&2
fi

ENABLE_SIGNUP="$(opt_bool enable_signup)"
DISABLE_SIGNUP="true"
[ "$ENABLE_SIGNUP" = "true" ] && DISABLE_SIGNUP="false"

SMTP_HOST="$(opt smtp_host)"
SMTP_PORT="$(opt smtp_port)"
SMTP_USER="$(opt smtp_user)"
SMTP_PASSWORD="$(opt smtp_password)"
SMTP_TLS_KIND="$(opt smtp_tls_kind)"
[ -z "$SMTP_TLS_KIND" ] && SMTP_TLS_KIND="wrapper"
SMTP_ADMIN_EMAIL="$(opt smtp_admin_email)"
[ -z "$SMTP_ADMIN_EMAIL" ] && SMTP_ADMIN_EMAIL="$ADMIN_EMAIL"
MAILER_AUTOCONFIRM="true"
[ -n "$SMTP_HOST" ] && MAILER_AUTOCONFIRM="false"

GOOGLE_ENABLED="$(opt_bool oauth_google_enabled)"
GOOGLE_CLIENT_ID="$(opt oauth_google_client_id)"
GOOGLE_SECRET="$(opt oauth_google_client_secret)"
GITHUB_ENABLED="$(opt_bool oauth_github_enabled)"
GITHUB_CLIENT_ID="$(opt oauth_github_client_id)"
GITHUB_SECRET="$(opt oauth_github_client_secret)"

LOG_LEVEL="$(opt log_level)"
[ -z "$LOG_LEVEL" ] && LOG_LEVEL="info"

cat > "$ENV_FILE" <<EOF
export APPFLOWY_BASE_URL="${BASE_URL}"

export POSTGRES_USER="postgres"
export POSTGRES_DB="postgres"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD}"
export APPFLOWY_DATABASE_URL="postgres://postgres:${POSTGRES_PASSWORD}@127.0.0.1:5432/postgres"

export GOTRUE_JWT_SECRET="${GOTRUE_JWT_SECRET}"
export GOTRUE_JWT_EXP="7200"
export GOTRUE_ADMIN_EMAIL="${ADMIN_EMAIL}"
export GOTRUE_ADMIN_PASSWORD="${ADMIN_PASSWORD}"
export GOTRUE_DISABLE_SIGNUP="${DISABLE_SIGNUP}"
export GOTRUE_MAILER_AUTOCONFIRM="${MAILER_AUTOCONFIRM}"
export GOTRUE_SMTP_HOST="${SMTP_HOST}"
export GOTRUE_SMTP_PORT="${SMTP_PORT}"
export GOTRUE_SMTP_USER="${SMTP_USER}"
export GOTRUE_SMTP_PASS="${SMTP_PASSWORD}"
export GOTRUE_SMTP_ADMIN_EMAIL="${SMTP_ADMIN_EMAIL}"
export GOTRUE_EXTERNAL_GOOGLE_ENABLED="${GOOGLE_ENABLED}"
export GOTRUE_EXTERNAL_GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID}"
export GOTRUE_EXTERNAL_GOOGLE_SECRET="${GOOGLE_SECRET}"
export GOTRUE_EXTERNAL_GOOGLE_REDIRECT_URI="${BASE_URL}/gotrue/callback"
export GOTRUE_EXTERNAL_GITHUB_ENABLED="${GITHUB_ENABLED}"
export GOTRUE_EXTERNAL_GITHUB_CLIENT_ID="${GITHUB_CLIENT_ID}"
export GOTRUE_EXTERNAL_GITHUB_SECRET="${GITHUB_SECRET}"
export GOTRUE_EXTERNAL_GITHUB_REDIRECT_URI="${BASE_URL}/gotrue/callback"

export APPFLOWY_MAILER_SMTP_HOST="${SMTP_HOST}"
export APPFLOWY_MAILER_SMTP_PORT="${SMTP_PORT}"
export APPFLOWY_MAILER_SMTP_USERNAME="${SMTP_USER}"
export APPFLOWY_MAILER_SMTP_EMAIL="${SMTP_USER}"
export APPFLOWY_MAILER_SMTP_PASSWORD="${SMTP_PASSWORD}"
export APPFLOWY_MAILER_SMTP_TLS_KIND="${SMTP_TLS_KIND}"

export APPFLOWY_S3_ACCESS_KEY="${MINIO_ACCESS_KEY}"
export APPFLOWY_S3_SECRET_KEY="${MINIO_SECRET_KEY}"
export APPFLOWY_S3_BUCKET="appflowy"
export APPFLOWY_S3_USE_MINIO="true"
export APPFLOWY_S3_CREATE_BUCKET="true"
export APPFLOWY_S3_MINIO_URL="http://127.0.0.1:9000"
export APPFLOWY_S3_PRESIGNED_URL_ENDPOINT="${BASE_URL}/minio-api"
export APPFLOWY_S3_REGION="us-east-1"

export APPFLOWY_GOTRUE_BASE_URL="http://127.0.0.1:9999"
export APPFLOWY_GOTRUE_JWT_SECRET="${GOTRUE_JWT_SECRET}"
export APPFLOWY_GOTRUE_JWT_EXP="7200"
export APPFLOWY_REDIS_URI="redis://127.0.0.1:6379"
export APPFLOWY_ACCESS_CONTROL="true"
export APPFLOWY_DATABASE_MAX_CONNECTIONS="40"
export APPFLOWY_WEB_URL="${BASE_URL}"
export APPFLOWY_ENVIRONMENT="production"
export RUST_LOG="${LOG_LEVEL}"
export RUST_BACKTRACE="1"

export ADMIN_FRONTEND_REDIS_URL="redis://127.0.0.1:6379"
export ADMIN_FRONTEND_GOTRUE_URL="http://127.0.0.1:9999"
export ADMIN_FRONTEND_APPFLOWY_CLOUD_URL="http://127.0.0.1:8000"
export ADMIN_FRONTEND_PATH_PREFIX="/console"

export APPFLOWY_WORKER_REDIS_URL="redis://127.0.0.1:6379"
export APPFLOWY_WORKER_DATABASE_URL="postgres://postgres:${POSTGRES_PASSWORD}@127.0.0.1:5432/postgres"
export APPFLOWY_WORKER_DATABASE_NAME="postgres"
EOF
chmod 600 "$ENV_FILE"
echo "[appflowy] configuration rendered to ${ENV_FILE}"
