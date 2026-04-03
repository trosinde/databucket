# Databucket — Nutzung

## Voraussetzungen

- Docker und Docker Compose
- Python 3.11+
- `pip install boto3` (Minimum für CLI)
- `pip install s3fs pandas` (optional, für direkte pandas-Nutzung)

## Installation

```bash
git clone git@github.com:trosinde/databucket.git
cd databucket
./install.sh
```

Der Installer:
- Prüft ob Docker, Docker Compose und Python installiert sind
- Installiert `boto3` falls nicht vorhanden
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

## databucket CLI — Vollständige Referenz

### Service-Management

```bash
databucket start              # Services starten
databucket stop               # Services stoppen
databucket status             # Status aller Container
databucket logs               # Logs (letzte 50 Zeilen)
databucket logs minio         # Logs eines einzelnen Service
databucket update             # Images aktualisieren & Neustart
databucket info               # Systemübersicht (Services, Buckets, Endpoints)
```

### Bucket-Verwaltung

```bash
databucket bucket list        # Alle Buckets auflisten
databucket bucket create raw  # Bucket anlegen
databucket bucket delete raw  # Bucket löschen (muss leer sein)
databucket bucket info raw    # Bucket-Statistik (Anzahl Objekte, Gesamtgröße)
```

Empfohlene Grundstruktur:

```bash
databucket bucket create raw          # Originaldaten, unveränderlich
databucket bucket create processed    # Transformierte/bereinigte Daten
databucket bucket create curated      # Analysefertige Daten
```

### Daten-Operationen

```bash
# Hochladen
databucket upload report.pdf raw documents/2026/04/report.pdf
databucket upload sensor.csv raw iot/2026/04/03/sensor.csv \
    --metadata source=gateway-01,format=csv \
    --tags project=alpha,status=unprocessed

# Auflisten
databucket ls raw
databucket ls raw documents/2026/

# Herunterladen
databucket download raw documents/2026/04/report.pdf ./report.pdf

# Objekt-Details (Metadata, Tags, Größe)
databucket inspect raw documents/2026/04/report.pdf
```

### Benutzerverwaltung

```bash
# Benutzer auflisten
databucket user list

# Benutzer anlegen
databucket user create analyst sicheres-passwort

# Policy zuweisen (Pflicht nach Erstellung!)
databucket user policy analyst readonly

# Benutzer-Details anzeigen
databucket user info analyst

# Benutzer deaktivieren / aktivieren
databucket user disable analyst
databucket user enable analyst

# Benutzer löschen
databucket user delete analyst
```

### Policies (Zugriffsrechte)

```bash
# Verfügbare Policies auflisten
databucket policy list

# Policy-Details anzeigen
databucket policy info readwrite
```

Eingebaute Policies:

| Policy | Berechtigung |
|--------|-------------|
| `readonly` | Lesen auf alle Buckets |
| `readwrite` | Lesen + Schreiben auf alle Buckets |
| `writeonly` | Nur Schreiben auf alle Buckets |
| `diagnostics` | Health/Info Endpoints |

Eigene Policies (z.B. Zugriff nur auf bestimmte Buckets) können über die MinIO Console erstellt werden.

### Backup

```bash
# Alle Daten lokal sichern (Standard: ./databucket-backup/)
databucket backup

# In ein bestimmtes Verzeichnis
databucket backup /mnt/backup/databucket-2026-04-03
```

### Typischer Workflow: Neuen Benutzer einrichten

```bash
# 1. Benutzer anlegen
databucket user create data-team geheim123!

# 2. Nur Lesezugriff zuweisen
databucket user policy data-team readonly

# 3. Prüfen
databucket user info data-team

# 4. Benutzer kann sich jetzt mit eigenen Credentials verbinden:
#    Access Key: data-team
#    Secret Key: geheim123!
#    Endpoint:   http://<server>:9000
```

## Python / boto3

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

# Objekt lesen
resp = s3.get_object(Bucket="raw", Key="data/file.json")
content = resp["Body"].read().decode("utf-8")

# Metadata und Tags abfragen
head = s3.head_object(Bucket="raw", Key="data/file.json")
print(head["Metadata"])

tags = s3.get_object_tagging(Bucket="raw", Key="data/file.json")
print(tags["TagSet"])
```

## pandas / s3fs

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

# Dateien auflisten
files = fs.ls("raw/documents/2026/")

# Ergebnis zurückschreiben
with fs.open("curated/report/summary.parquet", "wb") as f:
    df.to_parquet(f)
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
      "args": ["compose", "-f", "/opt/databucket/docker-compose.yaml",
               "exec", "mcp-server", "python", "server.py"],
      "env": {}
    }
  }
}
```

## Troubleshooting

### MinIO startet nicht

```bash
databucket logs minio
```

Häufige Ursache: `.env` fehlt oder Passwort zu kurz (MinIO erfordert min. 8 Zeichen).

### Connection refused

```bash
databucket status
```

### Access Denied

```bash
databucket info    # Prüft ob Credentials funktionieren
```

### Benutzer kann nicht zugreifen

```bash
databucket user info <name>     # Policy zugewiesen?
databucket user enable <name>   # Benutzer aktiv?
```
