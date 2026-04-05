#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${DATABUCKET_HOME:-/opt/databucket}"
NETWORK_NAME="databucket"

echo "=== databucket installer ==="
echo ""

# Check dependencies
for cmd in docker git python3; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: $cmd is required but not installed."
        exit 1
    fi
done

if ! docker compose version &>/dev/null; then
    echo "ERROR: docker compose plugin is required."
    exit 1
fi

if ! python3 -c "import boto3" 2>/dev/null; then
    echo "Installing boto3..."
    pip install --quiet boto3
fi

# Install directory
echo "Install directory: $INSTALL_DIR"
sudo mkdir -p "$INSTALL_DIR"
sudo chown "$(id -u):$(id -g)" "$INSTALL_DIR"

# Copy project files
echo "Copying files..."
cp -r "$SCRIPT_DIR/docker-compose.yaml" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/mcp-server" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/indexer" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/docs" "$INSTALL_DIR/" 2>/dev/null || true

# .env setup
if [ ! -f "$INSTALL_DIR/.env" ]; then
    echo ""
    echo "Setting up credentials..."
    read -rp "MinIO root user [admin]: " MINIO_USER
    MINIO_USER="${MINIO_USER:-admin}"
    read -rsp "MinIO root password (min 8 chars): " MINIO_PASS
    echo ""
    if [ ${#MINIO_PASS} -lt 8 ]; then
        echo "ERROR: Password must be at least 8 characters."
        exit 1
    fi
    cat > "$INSTALL_DIR/.env" <<EOF
MINIO_ROOT_USER=${MINIO_USER}
MINIO_ROOT_PASSWORD=${MINIO_PASS}
MINIO_API_PORT=9000
MINIO_CONSOLE_PORT=9001
QDRANT_PORT=6333
INDEXER_PORT=8900
EOF
    chmod 600 "$INSTALL_DIR/.env"
    echo "Credentials saved to $INSTALL_DIR/.env"
else
    echo "Using existing $INSTALL_DIR/.env"
fi

# Docker network
if ! docker network inspect "$NETWORK_NAME" &>/dev/null; then
    echo "Creating Docker network: $NETWORK_NAME"
    docker network create "$NETWORK_NAME"
fi

# Update docker-compose to use the network
if ! grep -q "networks:" "$INSTALL_DIR/docker-compose.yaml"; then
    cat >> "$INSTALL_DIR/docker-compose.yaml" <<'EOF'

networks:
  default:
    name: databucket
    external: true
EOF
fi

# Build and start
echo ""
echo "Building and starting services..."
cd "$INSTALL_DIR"
docker compose build
docker compose up -d

# Wait for healthy
echo "Waiting for MinIO to become healthy..."
for i in $(seq 1 30); do
    if docker compose ps --format json | grep -q '"healthy"'; then
        break
    fi
    sleep 1
done

# Create MCP service account
echo ""
echo "Creating MCP service account..."
MCP_KEY="${MCP_ACCESS_KEY:-mcp-service}"
MCP_SECRET="${MCP_SECRET_KEY:-$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")}"
_mc_setup() {
    docker compose exec -T minio mc alias set local http://localhost:9000 "$MINIO_USER" "$MINIO_PASS" --quiet 2>/dev/null || true
    docker compose exec -T minio mc admin user add local "$MCP_KEY" "$MCP_SECRET" 2>/dev/null || true
    docker compose exec -T minio mc admin policy attach local readwrite --user "$MCP_KEY" 2>/dev/null || true
}
source "$INSTALL_DIR/.env"
MINIO_USER="$MINIO_ROOT_USER"
MINIO_PASS="$MINIO_ROOT_PASSWORD"
_mc_setup

# Update .env with MCP credentials
if ! grep -q "MCP_ACCESS_KEY" "$INSTALL_DIR/.env"; then
    cat >> "$INSTALL_DIR/.env" <<EOF
MCP_ACCESS_KEY=${MCP_KEY}
MCP_SECRET_KEY=${MCP_SECRET}
EOF
fi

# Restart to pick up MCP credentials and start all services
docker compose up -d

# Wait for indexer to become healthy
echo "Waiting for indexer to start..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:${INDEXER_PORT:-8900}/health >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

# Configure MinIO webhook notifications for auto-indexing
echo ""
echo "Configuring auto-indexing (MinIO → Indexer)..."
_mc_setup_webhook() {
    docker compose exec -T minio mc alias set local http://localhost:9000 "$MINIO_USER" "$MINIO_PASS" --quiet 2>/dev/null || true
    # Set up webhook target pointing to the indexer service
    docker compose exec -T minio mc admin config set local notify_webhook:indexer \
        endpoint="http://indexer:8900/webhook" \
        queue_dir="" \
        queue_limit="0" \
        2>/dev/null || true
    # Restart MinIO to apply notification config
    docker compose exec -T minio mc admin service restart local 2>/dev/null || true
}
_mc_setup_webhook
sleep 3

# Enable notifications on existing buckets
_enable_bucket_notifications() {
    local buckets
    buckets=$(docker compose exec -T minio mc ls local/ 2>/dev/null | awk '{print $NF}' | tr -d '/')
    for b in $buckets; do
        [ -z "$b" ] && continue
        docker compose exec -T minio mc event add local/"$b" arn:minio:sqs::indexer:webhook \
            --event put,delete 2>/dev/null || true
        echo "  Auto-indexing enabled for bucket: $b"
    done
}
_enable_bucket_notifications

# Install CLI
echo ""
echo "Installing databucket CLI..."
cp "$SCRIPT_DIR/databucket" "$INSTALL_DIR/databucket"
chmod +x "$INSTALL_DIR/databucket"
if sudo ln -sf "$INSTALL_DIR/databucket" /usr/local/bin/databucket 2>/dev/null; then
    echo "CLI installed: databucket (in /usr/local/bin)"
else
    echo "Could not link to /usr/local/bin. Add $INSTALL_DIR to your PATH:"
    echo "  export PATH=\"$INSTALL_DIR:\$PATH\""
fi

echo ""
echo "=== databucket installed ==="
echo ""
echo "  MinIO API:     http://localhost:${MINIO_API_PORT:-9000}"
echo "  MinIO Console: http://localhost:${MINIO_CONSOLE_PORT:-9001}"
echo "  Qdrant:        http://localhost:${QDRANT_PORT:-6333}"
echo "  Indexer:       http://localhost:${INDEXER_PORT:-8900}"
echo ""
echo "  databucket bucket create raw"
echo "  databucket upload myfile.csv raw data/myfile.csv"
echo "  databucket search 'find invoices from 2025'"
echo "  databucket update          # pull latest & restart"
