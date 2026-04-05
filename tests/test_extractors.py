"""Unit tests for indexer text extractors — no external dependencies needed."""

import json
import sys
import os

# Add indexer to path so we can import extractors directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "indexer"))

from extractors import extract_text


class TestPlainText:
    def test_text_plain(self):
        body = b"Hello world, this is a test document."
        result = extract_text(body, "text/plain", "test.txt")
        assert result == "Hello world, this is a test document."

    def test_markdown(self):
        body = b"# Heading\n\nSome content here."
        result = extract_text(body, "text/plain", "readme.md")
        assert "# Heading" in result

    def test_yaml(self):
        body = b"key: value\nlist:\n  - item1\n  - item2"
        result = extract_text(body, "text/plain", "config.yaml")
        assert "key: value" in result

    def test_log_file(self):
        body = b"2025-01-01 ERROR Something failed\n2025-01-02 INFO All good"
        result = extract_text(body, "text/plain", "app.log")
        assert "ERROR" in result

    def test_utf8_with_special_chars(self):
        body = "Ümlauts: äöü, Straße, naïve".encode("utf-8")
        result = extract_text(body, "text/plain", "german.txt")
        assert "Ümlauts" in result

    def test_empty_body(self):
        result = extract_text(b"", "text/plain", "empty.txt")
        assert result == ""


class TestCSV:
    def test_basic_csv(self):
        body = b"name,age,city\nAlice,30,Berlin\nBob,25,Munich"
        result = extract_text(body, "text/csv", "data.csv")
        assert "Alice" in result
        assert "Berlin" in result

    def test_csv_by_extension(self):
        body = b"col1,col2\n1,2"
        result = extract_text(body, "application/octet-stream", "data.csv")
        assert "col1" in result

    def test_csv_row_limit(self):
        rows = ["header"] + [f"row{i}" for i in range(600)]
        body = "\n".join(rows).encode()
        result = extract_text(body, "text/csv", "big.csv")
        lines = result.strip().split("\n")
        assert len(lines) <= 501  # header + 500 rows

    def test_tsv(self):
        body = b"name\tage\nAlice\t30"
        result = extract_text(body, "text/tab-separated-values", "data.tsv")
        assert "Alice" in result


class TestJSON:
    def test_valid_json(self):
        data = {"report": "Annual summary", "year": 2025}
        body = json.dumps(data).encode()
        result = extract_text(body, "application/json", "report.json")
        assert "Annual summary" in result

    def test_json_by_extension(self):
        body = b'{"key": "value"}'
        result = extract_text(body, "application/octet-stream", "config.json")
        assert "key" in result

    def test_malformed_json(self):
        body = b"{invalid json here"
        result = extract_text(body, "application/json", "bad.json")
        assert result is not None  # should fallback to raw text

    def test_large_json_truncation(self):
        data = {"content": "x" * 60000}
        body = json.dumps(data).encode()
        result = extract_text(body, "application/json", "large.json")
        assert len(result) <= 50000


class TestXMLHTML:
    def test_xml(self):
        body = b"<root><item>Hello</item></root>"
        result = extract_text(body, "application/xml", "data.xml")
        assert "Hello" in result

    def test_html(self):
        body = b"<html><body><p>Test content</p></body></html>"
        result = extract_text(body, "text/html", "page.html")
        assert "Test content" in result

    def test_html_by_extension(self):
        body = b"<h1>Title</h1>"
        result = extract_text(body, "application/octet-stream", "page.htm")
        assert "Title" in result


class TestBinary:
    def test_binary_with_null_bytes(self):
        body = b"\x00\x01\x02\xff\xfe"
        result = extract_text(body, "application/octet-stream", "image.bin")
        assert result is None

    def test_binary_png(self):
        body = b"\x89PNG\r\n\x1a\n\x00\x00\x00"
        result = extract_text(body, "image/png", "photo.png")
        assert result is None

    def test_text_fallback(self):
        """Text without a known content-type should be extracted as text."""
        body = b"This is plain text without proper content type"
        result = extract_text(body, "application/octet-stream", "unknown.dat")
        assert "plain text" in result


class TestPDF:
    def test_pdf_without_pymupdf(self):
        """If PyMuPDF is not installed, PDF extraction returns None gracefully."""
        body = b"%PDF-1.4 fake pdf content"
        result = extract_text(body, "application/pdf", "doc.pdf")
        # Either None (no PyMuPDF) or some text (if installed)
        assert result is None or isinstance(result, str)
