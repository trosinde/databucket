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

## Stack

- MinIO (object storage)
- Python 3.12 (MCP server, CLI)
- boto3 / s3fs (S3 clients)
- Docker Compose (deployment)

## AIOS
This project uses AIOS for orchestrated development workflows.
Read .aios/agent-instructions.md for details.
