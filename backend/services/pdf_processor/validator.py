"""
VaaniPariksha - PDF Validator
Validates uploaded PDF files before processing.
"""
import os

MAX_PDF_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


class PDFValidationError(Exception):
    pass


def validate_pdf(file_path: str, max_size_bytes: int = MAX_PDF_SIZE_BYTES) -> dict:
    """
    Validate a PDF file.
    Returns dict with validation result.
    Raises PDFValidationError on failure.
    """
    result = {
        "valid": True,
        "filename": os.path.basename(file_path),
        "size_bytes": 0,
        "errors": [],
    }

    # --- Check existence ---
    if not os.path.exists(file_path):
        raise PDFValidationError(f"File not found: {file_path}")

    # --- Check size ---
    size = os.path.getsize(file_path)
    result["size_bytes"] = size
    if size == 0:
        raise PDFValidationError("File is empty.")
    if size > max_size_bytes:
        mb = max_size_bytes // (1024 * 1024)
        raise PDFValidationError(f"File exceeds {mb}MB limit. Got {size / 1024 / 1024:.1f}MB.")

    # --- Check extension ---
    ext = os.path.splitext(file_path)[1].lower()
    if ext != ".pdf":
        raise PDFValidationError(f"Invalid file extension: {ext}. Only .pdf allowed.")

    # --- Check PDF magic bytes (fallback) ---
    try:
        with open(file_path, "rb") as f:
            header = f.read(5)
        if header != b"%PDF-":
            raise PDFValidationError("File does not appear to be a valid PDF (bad magic bytes).")
    except IOError as e:
        raise PDFValidationError(f"Cannot read file: {e}")

    # --- Try to open with PyMuPDF for structural validation ---
    try:
        import fitz
        doc = fitz.open(file_path)
        page_count = doc.page_count
        doc.close()
        if page_count == 0:
            raise PDFValidationError("PDF has no pages.")
        result["page_count"] = page_count
    except Exception as e:
        raise PDFValidationError(f"PDF structure invalid: {e}")

    return result
