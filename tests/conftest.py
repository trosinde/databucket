"""Shared fixtures for databucket tests."""

import os
import time
import pytest
import boto3
from botocore.config import Config


@pytest.fixture(scope="session")
def s3_endpoint():
    return os.environ.get("S3_ENDPOINT", "http://localhost:9000")


@pytest.fixture(scope="session")
def s3_credentials():
    return {
        "aws_access_key_id": os.environ.get("S3_ACCESS_KEY", "minioadmin"),
        "aws_secret_access_key": os.environ.get("S3_SECRET_KEY", "minioadmin"),
    }


@pytest.fixture(scope="session")
def s3(s3_endpoint, s3_credentials):
    """S3 client connected to test MinIO instance."""
    client = boto3.client(
        "s3",
        endpoint_url=s3_endpoint,
        **s3_credentials,
        config=Config(signature_version="s3v4"),
    )
    # Wait for MinIO to be ready
    for _ in range(30):
        try:
            client.list_buckets()
            return client
        except Exception:
            time.sleep(1)
    raise RuntimeError("MinIO not reachable")


@pytest.fixture()
def test_bucket(s3):
    """Create a temporary test bucket, clean up after."""
    import uuid
    name = f"test-{uuid.uuid4().hex[:8]}"
    s3.create_bucket(Bucket=name)
    yield name
    # Cleanup: delete all objects then bucket
    resp = s3.list_objects_v2(Bucket=name)
    for obj in resp.get("Contents", []):
        s3.delete_object(Bucket=name, Key=obj["Key"])
    s3.delete_bucket(Bucket=name)
