"""Databucket MCP Server — thin wrapper around MinIO/S3."""

import os
import json

import boto3
from botocore.config import Config
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("databucket")

_s3 = None


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


@mcp.tool()
def list_buckets() -> str:
    """List all buckets in the databucket store."""
    resp = s3().list_buckets()
    return json.dumps([b["Name"] for b in resp["Buckets"]])


@mcp.tool()
def list_objects(bucket: str, prefix: str = "", max_keys: int = 100) -> str:
    """List objects in a bucket, optionally filtered by prefix."""
    resp = s3().list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=max_keys)
    objects = []
    for obj in resp.get("Contents", []):
        objects.append({
            "key": obj["Key"],
            "size": obj["Size"],
            "modified": obj["LastModified"].isoformat(),
        })
    return json.dumps(objects)


@mcp.tool()
def get_object_info(bucket: str, key: str) -> str:
    """Get metadata and tags for an object."""
    head = s3().head_object(Bucket=bucket, Key=key)
    tags_resp = s3().get_object_tagging(Bucket=bucket, Key=key)
    tags = {t["Key"]: t["Value"] for t in tags_resp["TagSet"]}
    return json.dumps({
        "key": key,
        "size": head["ContentLength"],
        "content_type": head.get("ContentType", ""),
        "modified": head["LastModified"].isoformat(),
        "metadata": head.get("Metadata", {}),
        "tags": tags,
    })


@mcp.tool()
def get_object_text(bucket: str, key: str, max_bytes: int = 1_000_000) -> str:
    """Read an object as text (up to max_bytes). For text files, CSV, JSON, etc."""
    resp = s3().get_object(Bucket=bucket, Key=key, Range=f"bytes=0-{max_bytes - 1}")
    return resp["Body"].read().decode("utf-8", errors="replace")


@mcp.tool()
def put_object(
    bucket: str,
    key: str,
    content: str,
    content_type: str = "application/octet-stream",
    metadata: dict[str, str] | None = None,
    tags: dict[str, str] | None = None,
) -> str:
    """Upload text content as an object. Use metadata and tags for discoverability."""
    kwargs = {
        "Bucket": bucket,
        "Key": key,
        "Body": content.encode("utf-8"),
        "ContentType": content_type,
    }
    if metadata:
        kwargs["Metadata"] = metadata
    if tags:
        from urllib.parse import urlencode
        kwargs["Tagging"] = urlencode(tags)
    resp = s3().put_object(**kwargs)
    return json.dumps({"etag": resp["ETag"], "key": key})


@mcp.tool()
def delete_object(bucket: str, key: str) -> str:
    """Delete an object from a bucket."""
    s3().delete_object(Bucket=bucket, Key=key)
    return json.dumps({"deleted": key})


@mcp.tool()
def create_bucket(bucket: str) -> str:
    """Create a new bucket."""
    s3().create_bucket(Bucket=bucket)
    return json.dumps({"created": bucket})


@mcp.tool()
def search_by_prefix(bucket: str, prefix: str, max_keys: int = 50) -> str:
    """Search objects by key prefix. Useful for finding files by path pattern."""
    resp = s3().list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=max_keys)
    results = []
    for obj in resp.get("Contents", []):
        results.append({"key": obj["Key"], "size": obj["Size"]})
    return json.dumps(results)


if __name__ == "__main__":
    mcp.run()
