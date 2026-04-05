"""End-to-end tests for the databucket CLI."""

import os
import subprocess
import pytest

CLI = os.path.join(os.path.dirname(__file__), "..", "databucket")
ENV = {
    **os.environ,
    "DATABUCKET_HOME": os.environ.get("DATABUCKET_HOME", "/opt/databucket"),
}


def run(args, check=True):
    """Run databucket CLI command and return result."""
    result = subprocess.run(
        [CLI] + args,
        capture_output=True,
        text=True,
        env=ENV,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"databucket {' '.join(args)} failed:\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
    return result


class TestHelp:
    def test_help(self):
        r = run(["help"])
        assert "databucket" in r.stdout
        assert "Service:" in r.stdout
        assert "Buckets:" in r.stdout
        assert "Users:" in r.stdout
        assert "Policies:" in r.stdout

    def test_unknown_command(self):
        r = run(["nonexistent"], check=False)
        assert r.returncode == 1
        assert "Unknown command" in r.stdout


class TestServiceManagement:
    def test_status(self):
        r = run(["status"])
        assert "minio" in r.stdout.lower() or r.returncode == 0

    def test_info(self):
        r = run(["info"])
        assert "databucket" in r.stdout
        assert "S3 API" in r.stdout


class TestBucketE2E:
    def test_bucket_lifecycle(self):
        # Create
        r = run(["bucket", "create", "e2e-test-bucket"])
        assert "Created" in r.stdout

        # List
        r = run(["bucket", "list"])
        assert "e2e-test-bucket" in r.stdout

        # Info
        r = run(["bucket", "info", "e2e-test-bucket"])
        assert "Objects: 0" in r.stdout

        # Delete
        r = run(["bucket", "delete", "e2e-test-bucket"])
        assert "Deleted" in r.stdout

        # Verify gone
        r = run(["bucket", "list"])
        assert "e2e-test-bucket" not in r.stdout


class TestDataE2E:
    @pytest.fixture(autouse=True)
    def setup_bucket(self):
        run(["bucket", "create", "e2e-data-test"])
        yield
        # Cleanup: remove objects then bucket
        subprocess.run([CLI, "bucket", "delete", "e2e-data-test"],
                       capture_output=True, env=ENV)

    def test_upload_ls_download(self, tmp_path):
        # Create test file
        src = tmp_path / "test.csv"
        src.write_text("col1,col2\n1,2\n3,4\n")

        # Upload
        r = run(["upload", str(src), "e2e-data-test", "data/test.csv"])
        assert "Uploaded" in r.stdout

        # List
        r = run(["ls", "e2e-data-test"])
        assert "data/test.csv" in r.stdout

        # List with prefix
        r = run(["ls", "e2e-data-test", "data/"])
        assert "test.csv" in r.stdout

        # Download
        dst = tmp_path / "downloaded.csv"
        r = run(["download", "e2e-data-test", "data/test.csv", str(dst)])
        assert "Downloaded" in r.stdout
        assert dst.read_text() == "col1,col2\n1,2\n3,4\n"

        # Inspect
        r = run(["inspect", "e2e-data-test", "data/test.csv"])
        assert "Key:" in r.stdout
        assert "Size:" in r.stdout

        # Cleanup for bucket delete
        subprocess.run(
            [CLI, "ls", "e2e-data-test"],
            capture_output=True, env=ENV,
        )


class TestUserE2E:
    def test_user_lifecycle(self):
        # Create user
        r = run(["user", "create", "e2e-testuser", "testpass123!"])
        assert "Created" in r.stdout or "e2e-testuser" in r.stdout

        # List
        r = run(["user", "list"])
        assert "e2e-testuser" in r.stdout

        # Assign policy
        r = run(["user", "policy", "e2e-testuser", "readwrite"])
        assert "Attached" in r.stdout or r.returncode == 0

        # Info
        r = run(["user", "info", "e2e-testuser"])
        assert "e2e-testuser" in r.stdout

        # Disable
        r = run(["user", "disable", "e2e-testuser"])
        assert "Disabled" in r.stdout

        # Enable
        r = run(["user", "enable", "e2e-testuser"])
        assert "Enabled" in r.stdout

        # Delete
        r = run(["user", "delete", "e2e-testuser"])
        assert "Deleted" in r.stdout


class TestPolicyE2E:
    def test_policy_list(self):
        r = run(["policy", "list"])
        assert "readwrite" in r.stdout or "readonly" in r.stdout or r.returncode == 0

    def test_custom_policy_lifecycle(self, tmp_path):
        # Create policy JSON
        policy_file = tmp_path / "test-policy.json"
        policy_file.write_text("""{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": ["arn:aws:s3:::*"]
    }
  ]
}""")

        # Create
        r = run(["policy", "create", "e2e-test-policy", str(policy_file)])
        assert "Created" in r.stdout or r.returncode == 0

        # Info
        r = run(["policy", "info", "e2e-test-policy"])
        assert r.returncode == 0

        # Delete
        r = run(["policy", "delete", "e2e-test-policy"])
        assert "Deleted" in r.stdout or r.returncode == 0


class TestBackupE2E:
    def test_backup(self, tmp_path):
        # Setup: create bucket with data
        run(["bucket", "create", "e2e-backup-test"])
        src = tmp_path / "backup-data.txt"
        src.write_text("backup content")
        run(["upload", str(src), "e2e-backup-test", "file.txt"])

        # Backup
        backup_dir = tmp_path / "backup"
        r = run(["backup", str(backup_dir)])
        assert "Backup complete" in r.stdout

        # Verify
        backed_up = backup_dir / "e2e-backup-test" / "file.txt"
        assert backed_up.exists()
        assert backed_up.read_text() == "backup content"

        # Cleanup
        subprocess.run(
            [CLI, "bucket", "delete", "e2e-backup-test"],
            capture_output=True, env=ENV,
        )


class TestDataMetadataTagsE2E:
    @pytest.fixture(autouse=True)
    def setup_bucket(self):
        run(["bucket", "create", "e2e-meta-test"])
        yield
        subprocess.run([CLI, "bucket", "delete", "e2e-meta-test"],
                       capture_output=True, env=ENV)

    def test_upload_with_metadata_and_tags(self, tmp_path):
        src = tmp_path / "meta.txt"
        src.write_text("metadata test")
        r = run([
            "upload", str(src), "e2e-meta-test", "doc.txt",
            "--metadata", "source=test,format=txt",
            "--tags", "project=e2e,status=raw",
        ])
        assert "Uploaded" in r.stdout

        # Verify via inspect
        r = run(["inspect", "e2e-meta-test", "doc.txt"])
        assert "source" in r.stdout
        assert "project" in r.stdout


class TestUserKeyE2E:
    @pytest.fixture(autouse=True)
    def setup_user(self):
        run(["user", "create", "e2e-keyuser", "keypass12345!"])
        run(["user", "policy", "e2e-keyuser", "readwrite"])
        yield
        subprocess.run([CLI, "user", "delete", "e2e-keyuser"],
                       capture_output=True, env=ENV)

    def test_key_lifecycle(self):
        # Create key
        r = run(["user", "key", "create", "e2e-keyuser"])
        assert r.returncode == 0
        # Output should contain access key info
        assert "Access Key" in r.stdout or r.stdout.strip() != ""

        # List keys
        r = run(["user", "key", "list", "e2e-keyuser"])
        assert r.returncode == 0


class TestUserSwitchE2E:
    @pytest.fixture(autouse=True)
    def setup_user(self):
        run(["user", "create", "e2e-switchuser", "switchpass123!"])
        run(["user", "policy", "e2e-switchuser", "readwrite"])
        run(["bucket", "create", "e2e-switch-test"])
        yield
        subprocess.run([CLI, "bucket", "delete", "e2e-switch-test"],
                       capture_output=True, env=ENV)
        subprocess.run([CLI, "user", "delete", "e2e-switchuser"],
                       capture_output=True, env=ENV)

    def test_as_user_can_list(self):
        r = run(["--as", "e2e-switchuser", "--password", "switchpass123!", "bucket", "list"])
        assert r.returncode == 0
        assert "e2e-switch-test" in r.stdout

    def test_as_user_access_denied(self):
        # Create user with no policy
        run(["user", "create", "e2e-noaccess", "noaccess123!"])
        r = run(["--as", "e2e-noaccess", "--password", "noaccess123!", "bucket", "list"], check=False)
        # Should fail with access denied
        assert r.returncode != 0 or "Access Denied" in r.stderr or "AccessDenied" in r.stderr
        subprocess.run([CLI, "user", "delete", "e2e-noaccess"],
                       capture_output=True, env=ENV)


class TestSearchE2E:
    """E2E tests for semantic search (requires indexer running)."""

    @pytest.fixture(autouse=True)
    def setup_bucket(self):
        run(["bucket", "create", "e2e-search-test"])
        yield
        subprocess.run([CLI, "bucket", "delete", "e2e-search-test"],
                       capture_output=True, env=ENV)

    def _indexer_available(self):
        import urllib.request
        try:
            urllib.request.urlopen("http://localhost:8900/health", timeout=2)
            return True
        except Exception:
            return False

    def test_index_and_search(self, tmp_path):
        if not self._indexer_available():
            pytest.skip("Indexer not running")

        # Upload test file
        src = tmp_path / "searchable.txt"
        src.write_text("Artificial intelligence and machine learning in healthcare applications")
        run(["upload", str(src), "e2e-search-test", "ai-healthcare.txt"])

        # Index the bucket
        r = run(["index", "e2e-search-test"])
        assert "Indexed" in r.stdout

        # Search
        r = run(["search", "AI in healthcare"])
        assert "ai-healthcare.txt" in r.stdout

    def test_search_no_results(self):
        if not self._indexer_available():
            pytest.skip("Indexer not running")

        r = run(["search", "xyzzy_completely_unique_nonsense_query_12345"])
        # Should not error, may return "No results"
        assert r.returncode == 0

    def test_search_no_args(self):
        r = run(["search"], check=False)
        assert r.returncode == 1

    def test_index_no_args(self):
        r = run(["index"], check=False)
        assert r.returncode == 1


class TestUsageErrors:
    def test_bucket_no_args(self):
        r = run(["bucket"], check=False)
        assert r.returncode == 1

    def test_upload_no_args(self):
        r = run(["upload"], check=False)
        assert r.returncode == 1

    def test_download_no_args(self):
        r = run(["download"], check=False)
        assert r.returncode == 1

    def test_ls_no_args(self):
        r = run(["ls"], check=False)
        assert r.returncode == 1

    def test_user_no_args(self):
        r = run(["user"], check=False)
        assert r.returncode == 1

    def test_policy_no_args(self):
        r = run(["policy"], check=False)
        assert r.returncode == 1
