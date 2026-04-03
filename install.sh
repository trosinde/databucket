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
echo "  MinIO API:     http://localhost:9000"
echo "  MinIO Console: http://localhost:9001"
echo ""
echo "  databucket bucket create raw"
echo "  databucket upload myfile.csv raw data/myfile.csv"
echo "  databucket update          # pull latest & restart"
