# databucket

Unstructured data storage on MinIO (S3-compatible). TB-scale, Docker-deployed.

## Install

```bash
./install.sh
```

The installer sets up Docker network, credentials, builds and starts all services, and installs the `databucket` CLI to `/usr/local/bin`.

## Quick Start

```bash
databucket bucket create raw
databucket upload myfile.csv raw data/myfile.csv
databucket ls raw
databucket update    # pull latest images & restart
```

MinIO Console: `http://localhost:9001`

## CLI

```
databucket start/stop/status/logs    # service management
databucket update                     # pull & restart
databucket bucket list/create/delete  # bucket management
databucket upload/download/ls         # data operations
databucket help                       # show all commands
```

## Access

| Method | Use case |
|--------|----------|
| `databucket` CLI | Admin, upload/download, service management |
| `pandas` / `s3fs` | Data analysis |
| `boto3` | Automation, scripts |
| MCP Server | Claude, AI agents |
| MinIO Console | Browser management |

## Documentation

- [Architecture](docs/architecture.md) — components, data model, decisions
- [Usage](docs/usage.md) — setup, CLI, pandas, MCP, access management

## Stack

- [MinIO](https://min.io) — S3-compatible object storage
- Python 3.12 — MCP server, CLI
- Docker Compose — deployment
