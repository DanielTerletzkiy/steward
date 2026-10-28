"""Generated pictures and documents for the demo: flat clothing silhouettes and a small manual PDF."""

from __future__ import annotations

import io

COLOR_RGB = {
    "black": (38, 38, 42), "white": (240, 240, 236), "grey": (140, 142, 148), "navy": (36, 52, 92),
    "blue": (52, 96, 170), "light blue": (150, 186, 228), "beige": (214, 196, 160), "brown": (120, 80, 50),
    "olive": (106, 112, 60), "green": (56, 120, 80), "red": (180, 50, 50), "burgundy": (110, 30, 46),
    "pink": (230, 160, 180), "purple": (110, 70, 140), "yellow": (232, 200, 70), "orange": (226, 130, 50),
}  # fmt: skip

# Silhouettes on a 100x100 grid.
_TOP = [(30, 18), (42, 14), (58, 14), (70, 18), (90, 34), (80, 46), (72, 40), (72, 88), (28, 88), (28, 40), (20, 46), (10, 34)]
_LONG = [(30, 16), (42, 12), (58, 12), (70, 16), (84, 40), (90, 82), (79, 84), (72, 50), (72, 88), (28, 88), (28, 50), (21, 84), (10, 82), (16, 40)]
_COAT = [(30, 10), (42, 6), (58, 6), (70, 10), (84, 36), (90, 86), (79, 88), (73, 50), (74, 96), (26, 96), (27, 50), (21, 88), (10, 86), (16, 36)]
_TROUSERS = [(28, 8), (72, 8), (76, 94), (56, 94), (50, 36), (44, 94), (24, 94)]
_SHORTS = [(26, 22), (74, 22), (80, 70), (55, 72), (50, 46), (45, 72), (20, 70)]
_SHOE = [(8, 58), (12, 40), (28, 38), (40, 52), (78, 60), (92, 68), (92, 80), (8, 80)]
_BOOT = [(14, 80), (14, 20), (40, 20), (42, 56), (80, 62), (92, 70), (92, 84), (14, 84)]
_SCARF = [(20, 20), (80, 20), (80, 34), (62, 34), (62, 92), (48, 92), (48, 34), (20, 34)]
_HAT = [(20, 70), (24, 40), (36, 24), (64, 24), (76, 40), (80, 70)]

SHAPES = {
    "t-shirt": _TOP, "top": _TOP, "polo": _TOP, "shirt": _LONG, "blouse": _LONG, "long-sleeve": _LONG,
    "sweater": _LONG, "hoodie": _LONG, "cardigan": _LONG, "fleece": _LONG, "jacket": _COAT, "rain jacket": _COAT,
    "coat": _COAT, "blazer": _COAT, "jeans": _TROUSERS, "trousers": _TROUSERS, "chinos": _TROUSERS,
    "joggers": _TROUSERS, "leggings": _TROUSERS, "shorts": _SHORTS, "skirt": _SHORTS, "sneakers": _SHOE,
    "shoes": _SHOE, "sandals": _SHOE, "boots": _BOOT, "scarf": _SCARF, "hat": _HAT, "cap": _HAT,
}  # fmt: skip


def garment_picture(category: str, color: str, size: int = 640) -> bytes:
    """A flat, catalog-style silhouette of a piece of clothing in its main color, as PNG."""
    from PIL import Image, ImageDraw

    scale = size / 100
    image = Image.new("RGB", (size, size), (246, 246, 243))
    draw = ImageDraw.Draw(image)
    fill = COLOR_RGB.get(color, (140, 142, 148))
    outline = tuple(max(0, c - 40) for c in fill)
    points = [(x * scale, y * scale) for x, y in SHAPES.get(category, _TOP)]
    draw.polygon(points, fill=fill, outline=outline, width=max(2, size // 160))
    if category in ("jacket", "rain jacket", "coat", "cardigan", "blazer"):
        draw.line([(50 * scale, 10 * scale), (50 * scale, 94 * scale)], fill=outline, width=max(2, size // 200))
    if category == "jeans":
        draw.line([(30 * scale, 14 * scale), (70 * scale, 14 * scale)], fill=(200, 160, 80), width=max(1, size // 300))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def manual_pdf(title: str, pages: list[str]) -> bytes:
    """A minimal text PDF (Helvetica, one block of lines per page) that pdfplumber can read back."""
    objects: list[bytes] = []
    page_ids = []
    font_id = 3
    objects.append(b"")  # 1: catalog, filled in below
    objects.append(b"")  # 2: page tree
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for number, body in enumerate(pages, start=1):
        lines = [title, f"Page {number}", ""] + body.split("\n")
        stream = ["BT /F1 11 Tf 56 780 Td 15 TL"]
        for line in lines:
            safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream.append(f"({safe}) Tj T*")
        stream.append("ET")
        content = "\n".join(stream).encode("latin-1", "replace")
        objects.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        content_id = len(objects)
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 %d 0 R >> >> "
            b"/Contents %d 0 R >>" % (font_id, content_id)
        )
        page_ids.append(len(objects))
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{i} 0 R" for i in page_ids).encode()
    objects[1] = b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % len(page_ids)

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % index + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref))
    return out.getvalue()
