import fitz  # PyMuPDF
import docx
import os
from typing import Tuple

def extract_text_from_file(path: str, content_type: str = None) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf" or (content_type and "pdf" in content_type):
        return _extract_pdf(path)
    if ext in [".docx", ".doc"] or (content_type and "word" in (content_type or "")):
        return _extract_docx(path)
    if ext in [".txt"]:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    # epub support could be added
    return ""

def _extract_pdf(path: str) -> str:
    text = []
    doc = fitz.open(path)
    for page in doc:
        text.append(page.get_text())
    doc.close()
    return "\n\n".join(text)

def _extract_docx(path: str) -> str:
    doc = docx.Document(path)
    paragraphs = [p.text for p in doc.paragraphs]
    return "\n\n".join(paragraphs)