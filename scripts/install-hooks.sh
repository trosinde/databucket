#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
HOOKS_DIR="$PROJECT_DIR/.git/hooks"

echo "Installing git hooks..."

# Pre-commit: run local unit tests
cat > "$HOOKS_DIR/pre-commit" <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(git rev-parse --show-toplevel)"

echo "Running local tests before commit..."

# Start test MinIO if not running
if ! curl -sf http://localhost:9000/minio/health/live >/dev/null 2>&1; then
    echo "Starting test MinIO..."
    docker compose -f "$PROJECT_DIR/docker-compose.test.yaml" up -d
    for i in $(seq 1 30); do
        if curl -sf http://localhost:9000/minio/health/live >/dev/null 2>&1; then break; fi
        sleep 1
    done
fi

export S3_ENDPOINT=http://localhost:9000
export S3_ACCESS_KEY=minioadmin
export S3_SECRET_KEY=minioadmin

python3 -m pytest "$PROJECT_DIR/tests/test_mcp_server.py" -v --tb=short

echo "Local tests passed."
HOOK

chmod +x "$HOOKS_DIR/pre-commit"
echo "Installed: pre-commit hook (runs unit tests before every commit)"
echo ""
echo "Flow:"
echo "  git commit  → local unit tests (pre-commit hook)"
echo "  git push    → pve3 e2e tests (GitHub Actions)"
echo "  e2e pass    → auto-merge development → main"
