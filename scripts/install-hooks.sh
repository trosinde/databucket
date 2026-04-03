#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
HOOKS_DIR="$PROJECT_DIR/.git/hooks"

echo "Installing git hooks..."

cat > "$HOOKS_DIR/pre-push" <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail

echo "Running pre-push tests..."

SCRIPT_DIR="$(git rev-parse --show-toplevel)/scripts"
"$SCRIPT_DIR/test.sh" --all

echo "All tests passed. Pushing..."
HOOK

chmod +x "$HOOKS_DIR/pre-push"
echo "Installed: pre-push hook (runs all tests before push)"
