"""Image helpers. The vendor upload path accepts both PDF and image input
(brief 0.5: documents arrive as JPEG/HEIC-converted photos, not clean PDFs).
Images are normalized to a single-page PDF so the rest of the pipeline
(render -> layout -> crop -> OCR) is format-agnostic.
"""

from pathlib import Path

import fitz

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


def is_image(filename: str) -> bool:
    return Path(filename).suffix.lower() in IMAGE_SUFFIXES


def image_bytes_to_pdf(data: bytes) -> bytes:
    """Wrap a single raster image into a one-page PDF (page sized to the image)."""
    img_doc = fitz.open(stream=data, filetype="image")
    try:
        pdf_bytes = img_doc.convert_to_pdf()
    finally:
        img_doc.close()
    return pdf_bytes


def images_to_pdf(images: list[bytes]) -> bytes:
    """Combine multiple raster images into one multi-page PDF."""
    out = fitz.open()
    try:
        for data in images:
            img_doc = fitz.open(stream=data, filetype="image")
            try:
                pdf_bytes = img_doc.convert_to_pdf()
            finally:
                img_doc.close()
            page_pdf = fitz.open("pdf", pdf_bytes)
            out.insert_pdf(page_pdf)
            page_pdf.close()
        return out.tobytes()
    finally:
        out.close()
