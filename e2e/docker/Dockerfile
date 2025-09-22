# All-in-One E2E Testing Image for MUXI Runtime
# Includes all services and the MUXI runtime itself
FROM python:3.10-slim

# Add PostgreSQL APT repository for version 17
RUN apt-get update && apt-get install -y gnupg wget lsb-release \
    && wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/postgresql-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql-keyring.gpg] http://apt.postgresql.org/pub/repos/apt/ $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # PostgreSQL 17 and pgvector extension
    postgresql-17 \
    postgresql-client-17 \
    postgresql-17-pgvector \
    # Build dependencies
    build-essential \
    gcc \
    g++ \
    make \
    # System utilities
    curl \
    wget \
    git \
    supervisor \
    netcat-openbsd \
    # Image processing
    poppler-utils \
    tesseract-ocr \
    # Audio/Video processing
    ffmpeg \
    # Magic file detection
    libmagic1 \
    # Clean up
    && rm -rf /var/lib/apt/lists/*

# Set PostgreSQL environment
ENV PGDATA=/var/lib/postgresql/17/main
ENV PATH="/usr/lib/postgresql/17/bin:${PATH}"

# Create necessary directories (don't create PostgreSQL data dir, initdb will do it)
RUN mkdir -p /app /data /logs /var/run/postgresql /var/lib/postgresql/17 \
    && chown -R postgres:postgres /var/lib/postgresql /var/run/postgresql /logs

# Install Python packages for services
RUN pip install --no-cache-dir \
    faissx \
    fastapi \
    uvicorn \
    httpx \
    aiofiles

# Copy and install MUXI runtime requirements
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Install additional test requirements
RUN pip install --no-cache-dir \
    pytest>=7.0.0 \
    pytest-asyncio>=0.21.0 \
    pytest-timeout>=2.1.0 \
    pytest-xdist>=3.0.0 \
    pytest-cov>=4.0.0 \
    pytest-benchmark>=4.0.0 \
    pytest-mock>=3.10.0

# Download spaCy model (required by some dependencies)
RUN python -m spacy download en_core_web_sm || true

# Copy utility scripts (ensure destination is a directory)
COPY e2e/utils/webhook_server.py e2e/utils/a2a_registry.py /app/utils/

# Create proper user for running services (security improvement)
RUN useradd -m -u 1000 muxi && \
    mkdir -p /app/test-formations && \
    chown -R muxi:muxi /app

# Create FAISSx auth configuration
RUN echo '{"auth_key": "test-auth-key"}' > /app/faissx-auth.json

# Initialize PostgreSQL database during build
USER postgres
RUN rm -rf /var/lib/postgresql/17/main/* 2>/dev/null || true \
    && /usr/lib/postgresql/17/bin/initdb -D /var/lib/postgresql/17/main \
    && echo "listen_addresses = '*'" >> /var/lib/postgresql/17/main/postgresql.conf \
    && echo "max_connections = 200" >> /var/lib/postgresql/17/main/postgresql.conf \
    && echo "shared_buffers = 256MB" >> /var/lib/postgresql/17/main/postgresql.conf \
    && echo "host    all             all             0.0.0.0/0               trust" >> /var/lib/postgresql/17/main/pg_hba.conf \
    && echo "local   all             all                                     trust" >> /var/lib/postgresql/17/main/pg_hba.conf \
    && /usr/lib/postgresql/17/bin/pg_ctl -D /var/lib/postgresql/17/main -l /tmp/postgres.log start \
    && sleep 5 \
    && createdb muxi_test \
    && createuser muxi \
    && psql -c "GRANT ALL PRIVILEGES ON DATABASE muxi_test TO muxi;" \
    && psql -d muxi_test -c "CREATE EXTENSION IF NOT EXISTS vector;" \
    && /usr/lib/postgresql/17/bin/pg_ctl -D /var/lib/postgresql/17/main stop

USER root

# Create supervisor configuration
RUN cat > /etc/supervisor/conf.d/supervisord.conf <<EOF
[supervisord]
nodaemon=true
logfile=/logs/supervisord.log
pidfile=/var/run/supervisord.pid

[program:postgresql]
command=/usr/lib/postgresql/17/bin/postgres -D /var/lib/postgresql/17/main
user=postgres
autostart=true
autorestart=true
stdout_logfile=/logs/postgresql.log
stderr_logfile=/logs/postgresql.err
priority=1

[program:faissx-no-auth]
command=faissx.server run --port 45678
directory=/app
autostart=true
autorestart=true
stdout_logfile=/logs/faissx-no-auth.log
stderr_logfile=/logs/faissx-no-auth.err
priority=10

[program:faissx-with-auth]
command=faissx.server run --port 65432 --enable-auth --auth-file /app/faissx-auth.json
directory=/app
autostart=true
autorestart=true
stdout_logfile=/logs/faissx-with-auth.log
stderr_logfile=/logs/faissx-with-auth.err
priority=10

[program:webhook]
command=python /app/utils/webhook_server.py
directory=/app
environment=PYTHONUNBUFFERED="1"
autostart=true
autorestart=true
stdout_logfile=/logs/webhook.log
stderr_logfile=/logs/webhook.err
priority=20

[program:a2a-registry]
command=python /app/utils/a2a_registry.py
directory=/app
environment=PYTHONUNBUFFERED="1"
autostart=true
autorestart=true
stdout_logfile=/logs/a2a.log
stderr_logfile=/logs/a2a.err
priority=20
EOF

# Create health check script
RUN cat > /app/healthcheck.sh <<'EOF'
#!/bin/bash
# Health check for all services
# FAISSx uses ZeroMQ, check port is open
nc -z localhost 45678 || exit 1
nc -z localhost 65432 || exit 1
curl -f http://localhost:8765/health || exit 1
curl -f http://localhost:9090/health || exit 1
psql -U muxi -d muxi_test -c 'SELECT 1' > /dev/null 2>&1 || exit 1
exit 0
EOF

RUN chmod +x /app/healthcheck.sh

# Create entrypoint script
RUN cat > /app/entrypoint.sh <<'EOF'
#!/bin/bash
set -e

echo "Starting MUXI E2E Test Environment..."

# PostgreSQL is already initialized during build, just verify it exists
if [ ! -d "$PGDATA/base" ]; then
    echo "ERROR: PostgreSQL data directory not found!"
    echo "This should have been created during Docker build."
    exit 1
fi

echo "PostgreSQL data directory found."

# Wait for all services to be ready
wait_for_service() {
    local name=$1
    local url=$2
    local max_attempts=30
    local attempt=1

    echo "Waiting for $name..."
    while [ $attempt -le $max_attempts ]; do
        if curl -s -f "$url" > /dev/null 2>&1; then
            echo "$name is ready!"
            return 0
        fi
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done

    echo "$name failed to start!"
    return 1
}

# Start supervisor in background
/usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf &
SUPERVISOR_PID=$!

# Wait for services to start
sleep 10

# Check PostgreSQL is running
echo "Waiting for PostgreSQL..."
max_attempts=30
attempt=1
while [ $attempt -le $max_attempts ]; do
    if psql -U muxi -h localhost -d muxi_test -c 'SELECT 1' > /dev/null 2>&1; then
        echo "PostgreSQL is ready!"
        break
    fi
    echo -n "."
    sleep 2
    attempt=$((attempt + 1))
done

# FAISSx uses ZeroMQ, not HTTP - just check if port is open
echo "Waiting for FAISSx (no auth)..."
while ! nc -z localhost 45678; do
    echo -n "."
    sleep 2
done
echo "FAISSx (no auth) is ready!"

echo "Waiting for FAISSx (with auth)..."
while ! nc -z localhost 65432; do
    echo -n "."
    sleep 2
done
echo "FAISSx (with auth) is ready!"
# Wait for webhook and A2A with correct ports
wait_for_service "Webhook" "http://localhost:8765/health"
wait_for_service "A2A Registry" "http://localhost:9090/health"

echo "All services are ready!"

# If command provided, run it; otherwise keep container running
if [ $# -gt 0 ]; then
    exec "$@"
else
    echo "Ready for E2E testing. Run tests with:"
    echo "  docker exec -it muxi-e2e-test pytest tests/e2e/tests/ -v"
    tail -f /logs/*.log
fi
EOF

RUN chmod +x /app/entrypoint.sh

# Environment variables for testing
ENV POSTGRES_URI=postgresql://muxi:muxi_test_password@localhost:5432/muxi_test
ENV FAISSX_NO_AUTH_URL=http://localhost:45678
ENV FAISSX_WITH_AUTH_URL=http://localhost:65432
ENV A2A_REGISTRY_URL=http://localhost:9090
ENV WEBHOOK_URL=http://localhost:8765
ENV PYTHONPATH=/app/src:/app:$PYTHONPATH
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Secrets configuration (tests will use these)
ENV MUXI_SECRETS_PATH=/app/tests/assets/secrets.enc
ENV MUXI_SECRETS_KEY=/app/tests/assets/.key

# Test-specific environment variables
ENV PYTEST_TIMEOUT=300
ENV TEST_PARALLEL_WORKERS=4
ENV LOG_LEVEL=info

# Expose all service ports
EXPOSE 5432 45678 65432 8765 9090

# Health check using the dedicated script
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD /app/healthcheck.sh

# Set working directory for MUXI runtime
WORKDIR /app

# Entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]