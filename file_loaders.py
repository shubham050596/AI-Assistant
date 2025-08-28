# file_loaders.py
import os

def load_text(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".txt":
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    if ext == ".pdf":
        try:
            import pdfminer.high_level as pdf_high
            return pdf_high.extract_text(path) or ""
        except Exception:
            return ""

    if ext in (".docx", ".doc"):
        try:
            import docx
            doc = docx.Document(path)
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception:
            return ""

    return ""
