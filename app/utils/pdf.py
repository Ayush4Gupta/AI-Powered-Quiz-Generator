# pdf.py
from pathlib import Path
from typing import List
import pypdf

class PDFExtractionError(Exception): ...

def extract_text(pdf_path: Path) -> str:
    try:
        reader = pypdf.PdfReader(str(pdf_path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except (pypdf.errors.PdfReadError, FileNotFoundError) as exc:
        raise PDFExtractionError(f"Could not parse PDF: {exc}") from exc
