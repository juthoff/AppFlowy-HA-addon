#!/bin/bash
# Initialises the persistent Postgres data directory on first start,
# then makes sure the pgvector extension and the postgres password
# match the generated secret. Postgres is started/stopped temporarily
# here just for this bootstrap; the real long-running server is started
# afterwards by /etc/services.d/postgres/run.
set -euo pipefail
source /etc/appflowy/env

PGDATA=/data/postgres
PGBIN="$(pg_config --bindir 2>/dev/null || echo /usr/lib/postgresql/16/bin)"

if [ ! -s "${PGDATA}/PG_VERSION" ]; then
    echo "[appflowy] initialising Postgres data directory at ${PGDATA}"
    mkdir -p "$PGDATA"
    chown -R postgres:postgres "$PGDATA"
    chmod 700 "$PGDATA"
    s6-setuidgid postgres "${PGBIN}/initdb" -D "$PGDATA" --username=postgres --auth=trust --encoding=UTF8
fi
chown -R postgres:postgres "$PGDATA"
chmod 700 "$PGDATA"
mkdir -p /run/postgresql
chown postgres:postgres /run/postgresql

echo "[appflowy] starting Postgres temporarily to apply bootstrap SQL"
s6-setuidgid postgres "${PGBIN}/pg_ctl" -D "$PGDATA" -w -t 60 \
    -o "-c listen_addresses='' -c unix_socket_directories=/run/postgresql" start

s6-setuidgid postgres psql -v ON_ERROR_STOP=1 -U postgres <<-EOSQL
    ALTER USER postgres WITH PASSWORD '${POSTGRES_PASSWORD}';
    CREATE EXTENSION IF NOT EXISTS vector;
EOSQL

s6-setuidgid postgres "${PGBIN}/pg_ctl" -D "$PGDATA" -w -t 60 stop
echo "[appflowy] Postgres bootstrap complete"
