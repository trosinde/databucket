#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Parse args
RUN_E2E=false
COVERAGE=false
for arg in "$@"; do
    case "$arg" in
        --e2e) RUN_E2E=true ;;
        --coverage) COVERAGE=true ;;
        --all) RUN_E2E=true; COVERAGE=true ;;
    esac
done

echo "=== databucket test runner ==="

# Unit tests (always run, don't need running services)
echo ""
echo "--- Unit tests (MCP server) ---"

# Start test MinIO if not running
if ! curl -sf http://localhost:9000/minio/health/live >/dev/null 2>&1; then
    echo "Starting test MinIO..."
    docker compose -f docker-compose.test.yaml up -d
    echo "Waiting for MinIO..."
    for i in $(seq 1 30); do
        if curl -sf http://localhost:9000/minio/health/live >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done
fi

export S3_ENDPOINT=http://localhost:9000
export S3_ACCESS_KEY=minioadmin
export S3_SECRET_KEY=minioadmin

COV_ARGS=""
if [ "$COVERAGE" = true ]; then
    COV_ARGS="--cov=mcp-server --cov-report=term-missing --cov-report=html:htmlcov"
fi

python3 -m pytest tests/test_mcp_server.py -v $COV_ARGS

# E2E tests
if [ "$RUN_E2E" = true ]; then
    echo ""
    echo "--- E2E tests (CLI) ---"

    # Setup test .env for CLI
    DATABUCKET_TEST_HOME=$(mktemp -d)
    cp docker-compose.test.yaml "$DATABUCKET_TEST_HOME/docker-compose.yaml"
    cat > "$DATABUCKET_TEST_HOME/.env" <<EOF
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_API_PORT=9000
MINIO_CONSOLE_PORT=9001
EOF

    export DATABUCKET_HOME="$DATABUCKET_TEST_HOME"
    python3 -m pytest tests/test_cli_e2e.py -v $COV_ARGS

    rm -rf "$DATABUCKET_TEST_HOME"
fi

echo ""
echo "=== All tests passed ==="
