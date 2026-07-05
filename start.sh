#!/bin/sh
set -e

echo "=== Van List 2026 startup ==="
echo "DATABASE_URL prefix: $(echo $DATABASE_URL | cut -c1-30)..."

# Wait for PostgreSQL to be ready (up to 60s)
if echo "$DATABASE_URL" | grep -q "postgresql"; then
    echo "Waiting for database..."
    max=12
    i=0
    until python3 -c "
import os, sys
try:
    import psycopg2
    conn = psycopg2.connect(os.environ['DATABASE_URL'], connect_timeout=5)
    conn.close()
    print('DB ready')
except Exception as e:
    print(f'DB not ready: {e}')
    sys.exit(1)
" 2>&1; do
        i=$((i+1))
        if [ $i -ge $max ]; then
            echo "Database unavailable after 60s, aborting"
            exit 1
        fi
        echo "Retry $i/$max in 5s..."
        sleep 5
    done
fi

echo "=== Running migrations ==="
alembic upgrade head
echo "=== Migrations complete ==="

echo "=== Starting server on port ${PORT:-8000} ==="
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
