"""Generate PDF and scanned-image fixtures from the demo document.

These exist so the PDF and image ingestion paths are exercised by real files
rather than asserted to work.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "demo" / "DEMO_discharge_summary.txt"
DEMO = ROOT / "data" / "demo"


def make_pdf(lines, out):
    """A normal, text-layer PDF -- the common case."""
    c = canvas.Canvas(str(out), pagesize=A4)
    w, h = A4
    y = h - 50
    c.setFont("Courier", 9)
    for ln in lines:
        if y < 50:
            c.showPage()
            c.setFont("Courier", 9)
            y = h - 50
        c.drawString(45, y, ln[:95])
        y -= 11.5
    c.save()
    return out


def make_image(lines, out, width=1240):
    """A page raster with no text layer -- forces the OCR path."""
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 17)
    except OSError:
        font = ImageFont.load_default()
    line_h = 23
    img = Image.new("RGB", (width, 60 + line_h * len(lines)), "white")
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        d.text((40, 30 + i * line_h), ln, fill=(15, 15, 15), font=font)
    img.save(out, dpi=(200, 200))
    return out


def make_scanned_pdf(image_path, out):
    """An image wrapped in a PDF -- a scan, with no extractable text layer."""
    img = Image.open(image_path)
    w, h = A4
    scale = min((w - 60) / img.width, (h - 60) / img.height)
    c = canvas.Canvas(str(out), pagesize=A4)
    c.drawImage(str(image_path), 30, h - 30 - img.height * scale,
                width=img.width * scale, height=img.height * scale)
    c.save()
    return out


if __name__ == "__main__":
    lines = SRC.read_text(encoding="utf-8").splitlines()
    print("wrote", make_pdf(lines, DEMO / "DEMO_discharge_summary.pdf"))
    print("wrote", make_image(lines, DEMO / "DEMO_discharge_summary_scan.png"))
    print("wrote", make_scanned_pdf(DEMO / "DEMO_discharge_summary_scan.png",
                                    DEMO / "DEMO_discharge_summary_scanned.pdf"))
