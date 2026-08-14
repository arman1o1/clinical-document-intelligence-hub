"""Document ingestion.

The brief asks the prototype to accept "text, PDF, or image". Those are three
very different reliability regimes and the pipeline downstream deserves to know
which one it is looking at:

  .txt / .md   perfect fidelity
  .pdf         perfect fidelity IF the PDF has a text layer; a scanned PDF has
               none, and silently returning its two characters of whitespace as
               "the document" is the worst possible failure
  image        OCR, which introduces character-level noise that degrades every
               downstream grounding check

So ingestion returns the text *and* a provenance record. A scanned PDF is
detected and routed to OCR rather than passed through empty, and anything that
went through OCR is marked, so the UI can warn the reviewer that confidence
scores on this document are measured against an imperfect transcription.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

TEXT_SUFFIXES = {".txt", ".md", ".text"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}

# below this many characters per page we assume there is no real text layer
TEXT_LAYER_MIN_CHARS = 120


@dataclass
class Ingested:
    text: str
    source_kind: str                 # "text" | "pdf" | "pdf-scanned" | "image"
    pages: int = 1
    ocr_used: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def degraded(self) -> bool:
        """True when the text is a transcription rather than the document itself."""
        return self.ocr_used


def _ocr_available() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract  # noqa: F401
        return True
    except ImportError:
        return False


def _ocr_image(img) -> str:
    import pytesseract
    return pytesseract.image_to_string(img)


def _load_pdf(path: Path) -> Ingested:
    import pdfplumber

    notes, pages_text = [], []
    with pdfplumber.open(path) as pdf:
        n = len(pdf.pages)
        for page in pdf.pages:
            pages_text.append(page.extract_text() or "")
        text = "\n".join(pages_text).strip()

        if len(text) >= TEXT_LAYER_MIN_CHARS * max(1, n) // 2:
            return Ingested(text=text, source_kind="pdf", pages=n, notes=notes)

        # No usable text layer -> almost certainly a scan.
        notes.append(f"No text layer found ({len(text)} chars across {n} page(s)).")
        if not _ocr_available():
            raise RuntimeError(
                f"{path.name} appears to be a scanned PDF with no text layer, and OCR is "
                "not available on this machine. Install Tesseract (`apt install tesseract-ocr` "
                "or `brew install tesseract`) plus `pip install pytesseract`, or supply a "
                "text-layer PDF."
            )
        notes.append("Fell back to OCR; downstream confidence is measured against the "
                     "transcription, not the original.")
        ocr_pages = []
        for page in pdf.pages:
            ocr_pages.append(_ocr_image(page.to_image(resolution=200).original))
        return Ingested(text="\n".join(ocr_pages).strip(), source_kind="pdf-scanned",
                        pages=n, ocr_used=True, notes=notes)


def _load_image(path: Path) -> Ingested:
    if not _ocr_available():
        raise RuntimeError(
            f"{path.name} is an image and OCR is not available on this machine. "
            "Install Tesseract (`apt install tesseract-ocr` or `brew install tesseract`) "
            "plus `pip install pytesseract`."
        )
    from PIL import Image
    text = _ocr_image(Image.open(path))
    return Ingested(
        text=text.strip(), source_kind="image", ocr_used=True,
        notes=["Text obtained by OCR; downstream confidence is measured against the "
               "transcription, not the original."],
    )


def load_document(path: str | Path) -> Ingested:
    """Read any supported document into text, recording how the text was obtained."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    suffix = p.suffix.lower()

    if suffix in TEXT_SUFFIXES:
        return Ingested(text=p.read_text(encoding="utf-8", errors="replace"),
                        source_kind="text")
    if suffix == ".pdf":
        return _load_pdf(p)
    if suffix in IMAGE_SUFFIXES:
        return _load_image(p)

    raise ValueError(
        f"Unsupported file type '{suffix}'. Supported: "
        f"{', '.join(sorted(TEXT_SUFFIXES | IMAGE_SUFFIXES | {'.pdf'}))}"
    )


def load_bytes(data: bytes, filename: str) -> Ingested:
    """Same, for an in-memory upload (Streamlit)."""
    import tempfile
    suffix = Path(filename).suffix.lower() or ".txt"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
        fh.write(data)
        tmp = Path(fh.name)
    try:
        return load_document(tmp)
    finally:
        tmp.unlink(missing_ok=True)
