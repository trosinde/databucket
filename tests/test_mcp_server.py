"""Unit tests for the MCP server S3 operations."""

import json
import pytest


class TestListBuckets:
    def test_list_empty(self, s3):
        resp = s3.list_buckets()
        assert "Buckets" in resp

    def test_list_after_create(self, s3, test_bucket):
        resp = s3.list_buckets()
        names = [b["Name"] for b in resp["Buckets"]]
        assert test_bucket in names


class TestBucketCRUD:
    def test_create_and_delete(self, s3):
        s3.create_bucket(Bucket="test-crud-bucket")
        names = [b["Name"] for b in s3.list_buckets()["Buckets"]]
        assert "test-crud-bucket" in names
        s3.delete_bucket(Bucket="test-crud-bucket")
        names = [b["Name"] for b in s3.list_buckets()["Buckets"]]
        assert "test-crud-bucket" not in names

    def test_delete_nonexistent_raises(self, s3):
        with pytest.raises(Exception):
            s3.delete_bucket(Bucket="nonexistent-bucket-xyz")


class TestObjectCRUD:
    def test_put_and_get(self, s3, test_bucket):
        s3.put_object(Bucket=test_bucket, Key="test.txt", Body=b"hello world")
        resp = s3.get_object(Bucket=test_bucket, Key="test.txt")
        assert resp["Body"].read() == b"hello world"

    def test_put_with_metadata(self, s3, test_bucket):
        s3.put_object(
            Bucket=test_bucket,
            Key="meta.txt",
            Body=b"data",
            Metadata={"source": "test", "format": "txt"},
        )
        head = s3.head_object(Bucket=test_bucket, Key="meta.txt")
        assert head["Metadata"]["source"] == "test"
        assert head["Metadata"]["format"] == "txt"

    def test_put_with_tags(self, s3, test_bucket):
        from urllib.parse import urlencode
        s3.put_object(
            Bucket=test_bucket,
            Key="tagged.txt",
            Body=b"data",
            Tagging=urlencode({"project": "alpha", "status": "raw"}),
        )
        tags_resp = s3.get_object_tagging(Bucket=test_bucket, Key="tagged.txt")
        tags = {t["Key"]: t["Value"] for t in tags_resp["TagSet"]}
        assert tags["project"] == "alpha"
        assert tags["status"] == "raw"

    def test_delete_object(self, s3, test_bucket):
        s3.put_object(Bucket=test_bucket, Key="to-delete.txt", Body=b"bye")
        s3.delete_object(Bucket=test_bucket, Key="to-delete.txt")
        resp = s3.list_objects_v2(Bucket=test_bucket, Prefix="to-delete.txt")
        assert resp.get("KeyCount", 0) == 0

    def test_get_nonexistent_raises(self, s3, test_bucket):
        with pytest.raises(Exception):
            s3.get_object(Bucket=test_bucket, Key="does-not-exist")


class TestListObjects:
    def test_list_empty_bucket(self, s3, test_bucket):
        resp = s3.list_objects_v2(Bucket=test_bucket)
        assert resp.get("KeyCount", 0) == 0

    def test_list_with_objects(self, s3, test_bucket):
        s3.put_object(Bucket=test_bucket, Key="a.txt", Body=b"a")
        s3.put_object(Bucket=test_bucket, Key="b.txt", Body=b"b")
        resp = s3.list_objects_v2(Bucket=test_bucket)
        keys = [obj["Key"] for obj in resp["Contents"]]
        assert "a.txt" in keys
        assert "b.txt" in keys

    def test_list_with_prefix(self, s3, test_bucket):
        s3.put_object(Bucket=test_bucket, Key="docs/a.txt", Body=b"a")
        s3.put_object(Bucket=test_bucket, Key="data/b.txt", Body=b"b")
        resp = s3.list_objects_v2(Bucket=test_bucket, Prefix="docs/")
        keys = [obj["Key"] for obj in resp["Contents"]]
        assert "docs/a.txt" in keys
        assert "data/b.txt" not in keys

    def test_list_max_keys(self, s3, test_bucket):
        for i in range(5):
            s3.put_object(Bucket=test_bucket, Key=f"file{i}.txt", Body=b"x")
        resp = s3.list_objects_v2(Bucket=test_bucket, MaxKeys=2)
        assert len(resp["Contents"]) == 2


class TestObjectInfo:
    def test_head_object(self, s3, test_bucket):
        s3.put_object(
            Bucket=test_bucket,
            Key="info.txt",
            Body=b"content",
            ContentType="text/plain",
        )
        head = s3.head_object(Bucket=test_bucket, Key="info.txt")
        assert head["ContentLength"] == 7
        assert head["ContentType"] == "text/plain"

    def test_content_type_default(self, s3, test_bucket):
        s3.put_object(Bucket=test_bucket, Key="binary.bin", Body=b"\x00\x01")
        head = s3.head_object(Bucket=test_bucket, Key="binary.bin")
        assert head["ContentLength"] == 2


class TestRangeRead:
    def test_range_read(self, s3, test_bucket):
        s3.put_object(Bucket=test_bucket, Key="large.txt", Body=b"0123456789")
        resp = s3.get_object(Bucket=test_bucket, Key="large.txt", Range="bytes=0-4")
        assert resp["Body"].read() == b"01234"


class TestUploadDownloadFile:
    def test_upload_download(self, s3, test_bucket, tmp_path):
        src = tmp_path / "upload.txt"
        src.write_text("upload content")
        s3.upload_file(str(src), test_bucket, "uploaded.txt")

        dst = tmp_path / "download.txt"
        s3.download_file(test_bucket, "uploaded.txt", str(dst))
        assert dst.read_text() == "upload content"

    def test_upload_large_file(self, s3, test_bucket, tmp_path):
        src = tmp_path / "large.bin"
        src.write_bytes(b"x" * 10_000_000)  # 10MB
        s3.upload_file(str(src), test_bucket, "large.bin")
        head = s3.head_object(Bucket=test_bucket, Key="large.bin")
        assert head["ContentLength"] == 10_000_000
