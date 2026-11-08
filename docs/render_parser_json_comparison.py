"""Render page 8 with the exact boxes used by the playground UI.

Run from the repository root with the llm-dev environment:
    python docs/render_parser_json_comparison.py
"""

from collections import Counter
from pathlib import Path
import json

import pymupdf
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_ID = "cee0be7be61840938cb4e0bf04b2ae8c"
DATA = ROOT / "backend" / "storage" / DOCUMENT_ID
OUTPUT = ROOT / "docs" / "assets" / "parser-json-comparison"
PAGE_INDEX = 7  # Page 8 in the PDF; JSON page_index starts at 0.
SCALE = 2
HEADER = 80

PARSERS = (
    ("pymupdf", "PyMuPDF"),
    ("docling", "Docling"),
    ("mineru", "MinerU"),
    ("marker", "Marker"),
    ("unstructured", "Unstructured"),
)

COLORS = {
    "heading": (249, 132, 28),
    "text": (31, 111, 226),
    "list": (14, 158, 143),
    "table": (226, 58, 107),
    "line": (126, 73, 207),
    "picture": (20, 148, 87),
}


def font(size: int, bold: bool = False):
    family = "segoeuib.ttf" if bold else "segoeui.ttf"
    location = Path("C:/Windows/Fonts") / family
    return ImageFont.truetype(str(location), size) if location.exists() else ImageFont.load_default()


def category(block: dict) -> str:
    kind = block["type"].lower()
    if kind in {"section_header", "sectionheader", "doc_title", "paragraph_title"}:
        return "heading"
    if kind == "table":
        return "table"
    if kind == "line":
        return "line"
    if kind == "list_item":
        return "list"
    if kind in {"image", "picture", "figure"}:
        return "picture"
    return "text"


def render(base: Image.Image, title: str, blocks: list[dict], filename: str, note: str = "") -> Image.Image:
    page = base.copy().convert("RGBA")
    overlay = Image.new("RGBA", page.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for block in blocks:
        bbox = block.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        color = COLORS[category(block)]
        rect = tuple(round(v * SCALE) for v in bbox)
        draw.rectangle(rect, fill=(*color, 25), outline=(*color, 255), width=4)
    page = Image.alpha_composite(page, overlay).convert("RGB")

    canvas = Image.new("RGB", (page.width, page.height + HEADER), "#f4f6fa")
    canvas.paste(page, (0, HEADER))
    header = ImageDraw.Draw(canvas)
    header.text((20, 12), title, font=font(31, True), fill="#16213a")
    detail = note or f"Page 8  |  {len(blocks)} displayed boxes"
    header.text((22, 49), detail, font=font(19), fill="#4d5b70")
    canvas.save(OUTPUT / filename, optimize=True)
    return canvas


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(DATA / "original.pdf") as pdf:
        pixmap = pdf[PAGE_INDEX].get_pixmap(matrix=pymupdf.Matrix(SCALE, SCALE), alpha=False)
        base = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

    images = [render(base, "Original page", [], "page8-original.png", "Page 8  |  no boxes")]
    for parser, title in PARSERS:
        normalized = json.loads((DATA / "results" / parser / "normalized.json").read_text(encoding="utf-8"))
        blocks = normalized["pages"][PAGE_INDEX]["blocks"]
        displayed = [block for block in blocks if block.get("level", "block") == "block"]
        images.append(render(base, title, displayed, f"page8-{parser}.png"))
        if parser == "marker":
            render(
                base,
                "Marker: all levels",
                blocks,
                "page8-marker-all.png",
                f"Page 8  |  {len(displayed)} blocks + {len(blocks) - len(displayed)} lines",
            )
        counts = dict(Counter(block["type"] for block in blocks))
        print(f"{title}: {len(blocks)} JSON nodes, {len(displayed)} default boxes, types={counts}")

    gap = 16
    cell_width = images[0].width // 2
    cell_height = images[0].height // 2
    montage = Image.new("RGB", (3 * cell_width + 4 * gap, 2 * cell_height + 3 * gap), "#dce2eb")
    for index, rendered in enumerate(images):
        tile = rendered.resize((cell_width, cell_height), Image.Resampling.LANCZOS)
        x = gap + (index % 3) * (cell_width + gap)
        y = gap + (index // 3) * (cell_height + gap)
        montage.paste(tile, (x, y))
    montage.save(OUTPUT / "page8-overview.png", optimize=True)
    print(f"Saved images to {OUTPUT}")


if __name__ == "__main__":
    main()
