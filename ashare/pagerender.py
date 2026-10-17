"""Render a document page as an image, with the matched text highlighted (v1.5).

Used by the Review page: the reviewer sees the source page next to the
extracted value. Rendering uses pypdfium2; images are encoded as PNG with
the standard library (zlib), which Tk 8.6 displays without Pillow.
"""
from __future__ import annotations

import base64
import re
import struct
import zlib
from pathlib import Path


def available() -> bool:
    try:
        import pypdfium2  # noqa: F401
        return True
    except Exception:
        return False


def encode_png(width: int, height: int, rgb: bytes, stride: int | None = None) -> bytes:
    """Minimal PNG encoder for 8-bit RGB data."""
    stride = stride or width * 3
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw += rgb[y * stride: y * stride + width * 3]

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))


def _probes(text: str) -> list[str]:
    """Search strings derived from a raw value, longest first."""
    t = re.sub(r"\s+", " ", text or "").strip()
    out = []
    for piece in [t[:40], t[:20]] + re.split(r"\s+", t)[:4]:
        piece = piece.strip()
        if len(piece) >= 2 and piece not in out:
            out.append(piece)
    return out


def render_page(path: str | Path, page_no: int, highlight: str | None = None, scale: float = 1.4) -> dict:
    """Return {'png': bytes, 'width', 'height', 'boxes': [(x0, y0, x1, y1) in image pixels], 'pages'}."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(path))
    try:
        n = len(pdf)
        page_no = max(1, min(int(page_no or 1), n))
        page = pdf[page_no - 1]
        w_pt, h_pt = page.get_size()
        bitmap = page.render(scale=scale, rev_byteorder=True)
        if bitmap.n_channels != 3:
            raise RuntimeError(f"unexpected bitmap with {bitmap.n_channels} channels")
        png = encode_png(bitmap.width, bitmap.height, bytes(bitmap.buffer), bitmap.stride)
        boxes = []
        if highlight:
            tp = page.get_textpage()
            try:
                for probe in _probes(highlight):
                    searcher = tp.search(probe)
                    hit = searcher.get_next()
                    if hit:
                        i, cnt = hit
                        for r in range(tp.count_rects(i, cnt)):
                            x0, y0, x1, y1 = tp.get_rect(r)
                            boxes.append((x0 * scale, (h_pt - y1) * scale, x1 * scale, (h_pt - y0) * scale))
                        break
            finally:
                tp.close()
        page.close()
        return {"png": png, "width": bitmap.width, "height": bitmap.height, "boxes": boxes, "pages": n,
                "page": page_no}
    finally:
        pdf.close()


def png_base64(png: bytes) -> str:
    return base64.b64encode(png).decode("ascii")
