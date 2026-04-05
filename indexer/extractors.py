"""Text extraction from various file formats."""

import csv
import io
import json


def extract_text(body: bytes, content_type: str, key: str) -> str | None:
    """Extract searchable text from an object. Returns None if unsupported."""
    ct = content_type.lower()
    kl = key.lower()

    # Plain text
    if "text/" in ct or kl.endswith((".txt", ".md", ".log", ".yaml", ".yml", ".toml")):
        return _decode(body)

    # CSV / TSV
    if "csv" in ct or kl.endswith((".csv", ".tsv")):
        return _extract_csv(body)

    # JSON
    if "json" in ct or kl.endswith(".json"):
        return _extract_json(body)

    # PDF
    if "pdf" in ct or kl.endswith(".pdf"):
        return _extract_pdf(body)

    # XML / HTML
    if "xml" in ct or "html" in ct or kl.endswith((".xml", ".html", ".htm")):
        return _decode(body)

    # Fallback: try as text
    try:
        text = body.decode("utf-8")
        if "\x00" in text:
            return None  # binary
        return text
    except UnicodeDecodeError:
        return None


def _decode(body: bytes) -> str:
    return body.decode("utf-8", errors="replace")


def _extract_csv(body: bytes) -> str:
    text = _decode(body)
    reader = csv.reader(io.StringIO(text))
    rows = []
    for i, row in enumerate(reader):
        rows.append(" ".join(row))
        if i >= 500:
            break
    return "\n".join(rows)


def _extract_json(body: bytes) -> str:
    text = _decode(body)
    try:
        data = json.loads(text)
        return json.dumps(data, indent=2, ensure_ascii=False, default=str)[:50000]
    except json.JSONDecodeError:
        return text


def _extract_pdf(body: bytes) -> str | None:
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=body, filetype="pdf")
        pages = []
        for page in doc:
            pages.append(page.get_text())
            if len(pages) >= 50:
                break
        doc.close()
        return "\n".join(pages) if pages else None
    except ImportError:
        # PyMuPDF not installed — skip PDFs
        return None
    except Exception:
        return None
