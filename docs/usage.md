# Databucket — Nutzung

## Voraussetzungen

- Docker und Docker Compose
- Python 3.11+
- `pip install boto3` (Minimum für CLI)
- `pip install s3fs pandas minio` (optional, für direkte pandas-Nutzung und Key-Management)

## Installation

```bash
# 1. Repository klonen
git clone git@github.com:trosinde/databucket.git
cd databucket

# 2. Installer ausführen
./install.sh
```

Der Installer:
- Prüft ob Docker und Docker Compose installiert sind
- Erstellt `/opt/databucket` als Installationsverzeichnis
- Fragt MinIO-Credentials ab (User + Passwort, min. 8 Zeichen)
- Erstellt das Docker-Netzwerk `databucket`
- Baut und startet MinIO + MCP Server
- Installiert das `databucket` CLI nach `/usr/local/bin`

Nach der Installation:
- MinIO API: `http://localhost:9000`
- MinIO Console: `http://localhost:9001` (Login mit den gewählten Credentials)

### Benutzerdefiniertes Installationsverzeichnis

```bash
DATABUCKET_HOME=/srv/databucket ./install.sh
```

### Manuelles Setup (ohne Installer)

```bash
cp .env.example .env       # Credentials eintragen
docker compose up -d       # Services starten
sudo ln -s $(pwd)/databucket /usr/local/bin/databucket
```

## Buckets anlegen

```bash
# Empfohlene Grundstruktur
databucket bucket create raw
databucket bucket create processed
databucket bucket create curated
```

## Dateien hochladen

### Per CLI

```bash
# Einfacher Upload
databucket upload report.pdf raw documents/2026/04/report.pdf

# Mit Metadata und Tags
databucket upload sensor.csv raw iot/2026/04/03/sensor.csv \
    --metadata source=gateway-01 format=csv \
    --tags project=alpha status=unprocessed
```

### Per Python / boto3

```python
import boto3
from botocore.config import Config

s3 = boto3.client(
    "s3",
    endpoint_url="http://localhost:9000",
    aws_access_key_id="dein-access-key",
    aws_secret_access_key="dein-secret-key",
    config=Config(signature_version="s3v4"),
)

# Upload
s3.upload_file("local-file.csv", "raw", "data/file.csv")

# Upload mit Metadata
s3.put_object(
    Bucket="raw",
    Key="data/file.json",
    Body=b'{"key": "value"}',
    ContentType="application/json",
    Metadata={"source": "api-import"},
)
```

## Dateien lesen

### Per CLI

```bash
# Objekte auflisten
databucket ls raw
databucket ls raw --prefix documents/2026/

# Herunterladen
databucket download raw documents/2026/04/report.pdf ./report.pdf
```

### Per pandas / s3fs

```python
import pandas as pd
import s3fs

fs = s3fs.S3FileSystem(
    endpoint_url="http://localhost:9000",
    key="dein-access-key",
    secret="dein-secret-key",
)

# CSV lesen
df = pd.read_csv(fs.open("raw/data/export.csv"))

# Parquet lesen
df = pd.read_parquet(fs.open("processed/results/analysis.parquet"))

# Alle Dateien in einem Pfad auflisten
files = fs.ls("raw/documents/2026/")

# Ergebnis zurückschreiben
with fs.open("curated/report/summary.parquet", "wb") as f:
    df.to_parquet(f)
```

### Per Python / boto3

```python
# Objekt als Text lesen
resp = s3.get_object(Bucket="raw", Key="data/file.json")
content = resp["Body"].read().decode("utf-8")

# Metadata und Tags abfragen
head = s3.head_object(Bucket="raw", Key="data/file.json")
print(head["Metadata"])  # {"source": "api-import"}

tags = s3.get_object_tagging(Bucket="raw", Key="data/file.json")
print(tags["TagSet"])
```

## MCP Server

Der MCP Server stellt 8 Tools für Claude und andere AI-Agenten bereit.

### Verfügbare Tools

| Tool | Parameter | Beschreibung |
|------|-----------|--------------|
| `list_buckets` | — | Alle Buckets auflisten |
| `list_objects` | bucket, prefix?, max_keys? | Objekte auflisten |
| `get_object_info` | bucket, key | Metadata + Tags abrufen |
| `get_object_text` | bucket, key, max_bytes? | Textinhalt lesen (max 1 MB) |
| `put_object` | bucket, key, content, content_type?, metadata?, tags? | Text-Objekt hochladen |
| `delete_object` | bucket, key | Objekt löschen |
| `create_bucket` | bucket | Bucket anlegen |
| `search_by_prefix` | bucket, prefix, max_keys? | Nach Pfad-Prefix suchen |

### Konfiguration in Claude

```json
{
  "mcpServers": {
    "databucket": {
      "command": "docker",
      "args": ["compose", "-f", "/pfad/zu/databucket/docker-compose.yaml",
               "exec", "mcp-server", "python", "server.py"],
      "env": {}
    }
  }
}
```

## Zugriffsverwaltung

### Root Credentials

Definiert in `.env`. Haben vollen Zugriff auf alle Buckets und Admin-Funktionen.

### Weitere Benutzer anlegen

MinIO verwaltet Benutzer über den `mc` CLI-Client:

```bash
# mc installieren (einmalig)
docker compose exec minio mc alias set local http://localhost:9000 $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD

# Benutzer anlegen
docker compose exec minio mc admin user add local neuer-user sicheres-passwort

# Policy zuweisen
docker compose exec minio mc admin policy attach local readwrite --user neuer-user

# Nur Lesezugriff
docker compose exec minio mc admin policy attach local readonly --user neuer-user
```

### Eingebaute Policies

| Policy | Berechtigung |
|--------|-------------|
| `readwrite` | Lesen + Schreiben auf alle Buckets |
| `readonly` | Nur Lesen auf alle Buckets |
| `writeonly` | Nur Schreiben auf alle Buckets |
| `diagnostics` | Health/Info Endpoints |

Eigene Policies (z.B. Zugriff nur auf bestimmte Buckets) können über die MinIO Console oder `mc admin policy create` erstellt werden.

## Troubleshooting

### MinIO startet nicht

```bash
docker compose logs minio
```

Häufige Ursache: `.env` fehlt oder Passwort zu kurz (MinIO erfordert min. 8 Zeichen).

### Connection refused

Prüfe ob der Port korrekt ist und MinIO healthy:

```bash
docker compose ps
curl http://localhost:9000/minio/health/live
```

### Access Denied

Prüfe ob Access Key und Secret Key korrekt sind. Bei Env-Variablen:

```bash
source .env
databucket --access-key $MINIO_ROOT_USER --secret-key $MINIO_ROOT_PASSWORD bucket list
```
