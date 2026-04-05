"""Tests for the indexer service — text extraction and search."""

import json
import os
import pytest

INDEXER_URL = os.environ.get("INDEXER_URL", "http://localhost:8900")


def _http(method, path, body=None):
    """Simple HTTP helper using urllib."""
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError

    url = f"{INDEXER_URL}{path}"
    data = json.dumps(body).encode() if body else b""
    req = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        resp = urlopen(req, timeout=30)
        return json.loads(resp.read())
    except HTTPError:
        raise  # real errors should fail the test
    except (URLError, ConnectionError, OSError) as e:
        pytest.skip(f"Indexer not reachable at {INDEXER_URL}: {e}")


@pytest.fixture(scope="module")
def indexer_available():
    """Skip all tests if the indexer is not running."""
    try:
        _http("GET", "/health")
    except Exception:
        pytest.skip("Indexer not running")


class TestIndexerHealth:
    def test_health(self, indexer_available):
        resp = _http("GET", "/health")
        assert resp["status"] == "ok"


class TestTextExtraction:
    """Test indexing and searching text objects end-to-end."""

    @pytest.fixture(autouse=True)
    def setup_bucket(self, s3, indexer_available):
        import uuid
        self.bucket = f"test-idx-{uuid.uuid4().hex[:8]}"
        s3.create_bucket(Bucket=self.bucket)
        yield
        # Cleanup
        resp = s3.list_objects_v2(Bucket=self.bucket)
        for obj in resp.get("Contents", []):
            s3.delete_object(Bucket=self.bucket, Key=obj["Key"])
        s3.delete_bucket(Bucket=self.bucket)

    def test_index_and_search_text(self, s3):
        # Upload a text file
        s3.put_object(
            Bucket=self.bucket,
            Key="notes/meeting.txt",
            Body=b"Discussion about quarterly revenue growth and market expansion strategy",
            ContentType="text/plain",
        )

        # Trigger manual index
        resp = _http("POST", f"/index/{self.bucket}")
        assert resp["indexed"] >= 1

        # Search
        resp = _http("POST", "/search", {"query": "revenue growth", "limit": 5})
        assert len(resp["results"]) >= 1
        assert any("meeting.txt" in r["key"] for r in resp["results"])

    def test_index_and_search_csv(self, s3):
        s3.put_object(
            Bucket=self.bucket,
            Key="data/sales.csv",
            Body=b"date,product,amount\n2025-01-15,Widget A,1500\n2025-02-20,Widget B,2300\n",
            ContentType="text/csv",
        )

        resp = _http("POST", f"/index/{self.bucket}")
        assert resp["indexed"] >= 1

        resp = _http("POST", "/search", {"query": "widget sales data", "limit": 5})
        assert len(resp["results"]) >= 1

    def test_index_and_search_json(self, s3):
        data = json.dumps({"report": "Annual financial summary", "year": 2025, "profit": 1200000})
        s3.put_object(
            Bucket=self.bucket,
            Key="reports/annual.json",
            Body=data.encode(),
            ContentType="application/json",
        )

        resp = _http("POST", f"/index/{self.bucket}")
        assert resp["indexed"] >= 1

        resp = _http("POST", "/search", {"query": "financial report", "limit": 5})
        assert len(resp["results"]) >= 1

    def test_search_with_bucket_filter(self, s3):
        s3.put_object(
            Bucket=self.bucket,
            Key="doc.txt",
            Body=b"Unique content about quantum computing research",
            ContentType="text/plain",
        )
        _http("POST", f"/index/{self.bucket}")

        # Search with bucket filter — should find it
        resp = _http("POST", "/search", {"query": "quantum computing", "bucket": self.bucket})
        assert len(resp["results"]) >= 1

        # Search with wrong bucket filter — should not find it
        resp = _http("POST", "/search", {"query": "quantum computing", "bucket": "nonexistent-bucket"})
        assert len(resp["results"]) == 0

    def test_binary_skipped(self, s3):
        s3.put_object(
            Bucket=self.bucket,
            Key="image.bin",
            Body=b"\x00\x01\x02\x03\xff\xfe",
            ContentType="application/octet-stream",
        )

        resp = _http("POST", f"/index/{self.bucket}")
        assert resp["skipped"] >= 1


class TestWebhook:
    """Test the MinIO webhook endpoint."""

    def test_webhook_created_event(self, s3, test_bucket, indexer_available):
        import time

        # Upload an object
        s3.put_object(
            Bucket=test_bucket,
            Key="webhook-test.txt",
            Body=b"Testing webhook integration for automatic indexing",
            ContentType="text/plain",
        )

        # Simulate the MinIO webhook event
        event = {
            "Records": [{
                "eventName": "s3:ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": test_bucket},
                    "object": {"key": "webhook-test.txt"},
                },
            }],
        }
        resp = _http("POST", "/webhook", event)
        assert resp["status"] == "accepted"

        # Wait for background processing
        time.sleep(3)

        # Verify it's searchable
        resp = _http("POST", "/search", {"query": "webhook automatic indexing", "bucket": test_bucket})
        assert len(resp["results"]) >= 1

    def test_webhook_removed_event(self, s3, test_bucket, indexer_available):
        import time

        # First index an object via manual index
        s3.put_object(
            Bucket=test_bucket,
            Key="to-remove.txt",
            Body=b"This object will be removed from the index",
            ContentType="text/plain",
        )
        _http("POST", f"/index/{test_bucket}")

        # Now send a remove event
        event_delete = {
            "Records": [{
                "eventName": "s3:ObjectRemoved:Delete",
                "s3": {
                    "bucket": {"name": test_bucket},
                    "object": {"key": "to-remove.txt"},
                },
            }],
        }
        resp = _http("POST", "/webhook", event_delete)
        assert resp["status"] == "accepted"

        # Wait for background processing
        time.sleep(2)
