# databucket

Unstructured data storage on MinIO (S3-compatible). TB-scale, Docker-deployed.

## Architecture

- **Storage:** MinIO (S3 API on :9000, Web Console on :9001)
- **MCP Server:** Python, boto3 — exposes S3 operations as MCP tools
- **CLI:** `databucket` — unified CLI for service management, buckets, upload/download
- **Access:** pandas via s3fs/boto3, REST via S3 API, AI via MCP

## Quick Start

```bash
./install.sh                           # full setup
databucket bucket create raw
databucket upload myfile.csv raw data/myfile.csv
databucket update                      # pull latest & restart
```

## Branching

- `main` — stable, auto-merged from development after all tests pass
- `development` — integration branch, PRs target this
- Feature branches → PR → `development` → (CI passes) → auto-merge to `main`

## Testing

```bash
scripts/test.sh --all          # unit + e2e + coverage locally
scripts/install-hooks.sh       # install pre-commit hook
```

Flow: commit (local tests) → push (pve3 e2e) → auto-merge to main
Test system: LXC 300 on pve3 (192.168.100.130)

## Stack

- MinIO (object storage)
- Python 3.12 (MCP server, CLI)
- boto3 / s3fs (S3 clients)
- Docker Compose (deployment)
- pytest (testing), GitHub Actions (CI)

## AIOS
This project uses AIOS for orchestrated development workflows.
Read .aios/agent-instructions.md for details.
