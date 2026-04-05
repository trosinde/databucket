"""Databucket Indexer — auto-indexes MinIO objects into Qdrant for semantic search."""

import logging
import os
import uuid
from urllib.parse import unquote

import boto3
import uvicorn
from botocore.config import Config
from fastapi import BackgroundTasks, FastAPI
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)
from sentence_transformers import SentenceTransformer

from extractors import extract_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("indexer")

COLLECTION = "databucket"
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2
MAX_TEXT_LENGTH = 10000  # chars to embed

app = FastAPI(title="databucket-indexer")

_model = None
_qdrant = None
_s3 = None


def model() -> SentenceTransformer:
    global _model
    if _model is None:
        log.info("Loading embedding model...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        log.info("Model loaded.")
    return _model


def qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(url=os.environ["QDRANT_URL"])
        _ensure_collection()
    return _qdrant


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client(
            "s3",
            endpoint_url=os.environ["S3_ENDPOINT"],
            aws_access_key_id=os.environ["S3_ACCESS_KEY"],
            aws_secret_access_key=os.environ["S3_SECRET_KEY"],
            config=Config(signature_version="s3v4"),
        )
    return _s3


def _ensure_collection():
    collections = [c.name for c in qdrant().get_collections().collections]
    if COLLECTION not in collections:
        qdrant().create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        log.info("Created Qdrant collection: %s", COLLECTION)


def _point_id(bucket: str, key: str) -> str:
    """Deterministic point ID from bucket+key."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"s3://{bucket}/{key}"))


def _index_object(bucket: str, key: str) -> bool:
    """Download, extract text, embed, and store. Returns True if indexed."""
    try:
        resp = s3().get_object(Bucket=bucket, Key=key)
        content_type = resp.get("ContentType", "")
        body = resp["Body"].read(5_000_000)  # 5MB max read
        content_length = resp.get("ContentLength", 0)
        if content_length > 5_000_000:
            log.info("Truncated to 5MB (actual: %d bytes): s3://%s/%s", content_length, bucket, key)

        text = extract_text(body, content_type, key)
        if not text or len(text.strip()) < 10:
            log.info("Skipped (no extractable text): s3://%s/%s", bucket, key)
            return False

        text_for_embedding = text[:MAX_TEXT_LENGTH]
        vector = model().encode(text_for_embedding).tolist()

        metadata = resp.get("Metadata", {})

        point = PointStruct(
            id=_point_id(bucket, key),
            vector=vector,
            payload={
                "bucket": bucket,
                "key": key,
                "content_type": content_type,
                "size": resp.get("ContentLength", 0),
                "modified": resp["LastModified"].isoformat(),
                "metadata": metadata,
                "text_preview": text[:500],
            },
        )
        qdrant().upsert(collection_name=COLLECTION, points=[point])
        log.info("Indexed: s3://%s/%s", bucket, key)
        return True

    except Exception:
        log.exception("Failed to index s3://%s/%s", bucket, key)
        return False


def _delete_from_index(bucket: str, key: str):
    """Remove an object from the index."""
    try:
        qdrant().delete(
            collection_name=COLLECTION,
            points_selector=[_point_id(bucket, key)],
        )
        log.info("Removed from index: s3://%s/%s", bucket, key)
    except Exception:
        log.exception("Failed to remove s3://%s/%s from index", bucket, key)


# --- MinIO Webhook endpoint ---


class MinIOEvent(BaseModel):
    EventName: str | None = None
    Key: str | None = None
    Records: list | None = None


def _process_webhook_records(records: list):
    """Process webhook records in background."""
    for record in records:
        event_name = record.get("eventName", "")
        s3_info = record.get("s3", {})
        bucket = s3_info.get("bucket", {}).get("name", "")
        key = s3_info.get("object", {}).get("key", "")

        if not bucket or not key:
            continue

        key = unquote(key)

        if "s3:ObjectCreated" in event_name:
            _index_object(bucket, key)
        elif "s3:ObjectRemoved" in event_name:
            _delete_from_index(bucket, key)


@app.post("/webhook")
async def webhook(event: MinIOEvent, background_tasks: BackgroundTasks):
    """Receive MinIO bucket notification webhooks."""
    records = event.Records or []
    if not records:
        return {"status": "no records"}

    background_tasks.add_task(_process_webhook_records, records)
    return {"status": "accepted", "records": len(records)}


# --- Search endpoint ---


class SearchRequest(BaseModel):
    query: str
    bucket: str | None = None
    limit: int = Field(default=10, ge=1, le=100)


@app.post("/search")
async def search(req: SearchRequest):
    """Semantic search across indexed objects."""
    vector = model().encode(req.query).tolist()

    filters = None
    if req.bucket:
        filters = Filter(
            must=[FieldCondition(key="bucket", match=MatchValue(value=req.bucket))]
        )

    results = qdrant().query_points(
        collection_name=COLLECTION,
        query=vector,
        query_filter=filters,
        limit=req.limit,
    )

    hits = []
    for point in results.points:
        hits.append({
            "bucket": point.payload["bucket"],
            "key": point.payload["key"],
            "score": point.score,
            "content_type": point.payload.get("content_type", ""),
            "size": point.payload.get("size", 0),
            "preview": point.payload.get("text_preview", ""),
        })

    return {"query": req.query, "results": hits}


# --- Index all objects in a bucket ---


@app.post("/index/{bucket}")
async def index_bucket(bucket: str):
    """Re-index all objects in a bucket."""
    paginator = s3().get_paginator("list_objects_v2")
    indexed = 0
    skipped = 0
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            if _index_object(bucket, obj["Key"]):
                indexed += 1
            else:
                skipped += 1
    return {"bucket": bucket, "indexed": indexed, "skipped": skipped}


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.environ.get("INDEXER_PORT", "8900"))
    # Pre-load model at startup
    model()
    uvicorn.run(app, host="0.0.0.0", port=port)
