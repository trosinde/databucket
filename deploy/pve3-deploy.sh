#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Deploy databucket to the test LXC on pve3
#
# Run from local machine:
#   deploy/pve3-deploy.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CT_IP="${CT_IP:-192.168.100.130}"
CT_USER="root"
TARGET="$CT_USER@$CT_IP"

echo "=== Deploying databucket to $TARGET ==="

# Copy project files
echo "Copying files..."
rsync -avz --exclude='.git' --exclude='.ssh' --exclude='.env' \
    --exclude='__pycache__' --exclude='htmlcov' --exclude='.aios' \
    --exclude='node_modules' --exclude='.venv' \
    "$PROJECT_DIR/" "$TARGET:/root/databucket/"

# Run installer on target
echo ""
echo "Running installer..."
ssh "$TARGET" bash <<'REMOTE_INSTALL'
set -euo pipefail
cd /root/databucket
./install.sh <<ANSWERS
admin
databucket-test-2026!
ANSWERS

# Create default buckets
echo ""
echo "Creating default buckets..."
databucket bucket create raw
databucket bucket create processed
databucket bucket create curated

echo ""
databucket info
REMOTE_INSTALL

echo ""
echo "=== Deployment complete ==="
echo ""
echo "  databucket API:     http://$CT_IP:9000"
echo "  databucket Console: http://$CT_IP:9001"
echo "  SSH:                ssh $TARGET"
echo ""
echo "  Run tests remotely:"
echo "    ssh $TARGET 'cd /root/databucket && scripts/test.sh --all'"
