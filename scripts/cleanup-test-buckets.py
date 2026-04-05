"""Clean up leftover test buckets from previous CI runs."""
import os
import boto3
from botocore.config import Config

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ.get("S3_ENDPOINT", "http://localhost:9000"),
    aws_access_key_id=os.environ.get("S3_ACCESS_KEY", "minioadmin"),
    aws_secret_access_key=os.environ.get("S3_SECRET_KEY", "minioadmin"),
    config=Config(signature_version="s3v4"),
)

for b in s3.list_buckets()["Buckets"]:
    name = b["Name"]
    if name.startswith("e2e-") or name.startswith("test-"):
        resp = s3.list_objects_v2(Bucket=name)
        for obj in resp.get("Contents", []):
            s3.delete_object(Bucket=name, Key=obj["Key"])
        s3.delete_bucket(Bucket=name)
        print(f"Cleaned up: {name}")
