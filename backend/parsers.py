"""Small adapters that turn parser output into page/block data for the UI."""

from __future__ import annotations

import importlib.util
import re
from html import unescape
from pathlib import Path


PARSERS = {
    "pymupdf": ("PyMuPDF", "pymupdf"),
    "docling": ("Docling", "docling"),
    "mineru": ("MinerU", "mineru"),
    "marker": ("Marker", "marker-pdf"),
    "unstructured": ("Unstructured", "unstructured[pdf]"),
}


def installed(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def page_sizes(pdf_path: Path) -> list[tuple[float, float]]:
    import pymupdf as fitz

    with fitz.open(pdf_path) as pdf:
        return [(float(page.rect.width), float(page.rect.height)) for page in pdf]


def empty_pages(sizes: list[tuple[float, float]]) -> list[dict]:
    return [
        {"page_index": i, "width": width, "height": height, "blocks": []}
        for i, (width, height) in enumerate(sizes)
    ]


def clean_bbox(bbox, width: float, height: float):
    if not bbox or len(bbox) != 4:
        return None
    try:
        x0, y0, x1, y1 = map(float, bbox)
    except (TypeError, ValueError):
        return None
    x0, x1 = sorted((max(0, min(width, x0)), max(0, min(width, x1))))
    y0, y1 = sorted((max(0, min(height, y0)), max(0, min(height, y1))))
    if x1 - x0 < 0.5 or y1 - y0 < 0.5:
        return None
    return [round(v, 2) for v in (x0, y0, x1, y1)]


def add_block(pages, parser, page_index, kind, text, bbox, *, polygon=None, level="block", source_id=None):
    if not isinstance(page_index, int) or not 0 <= page_index < len(pages):
        return
    page = pages[page_index]
    box = clean_bbox(bbox, page["width"], page["height"])
    if box is None:
        return
    blocks = page["blocks"]
    block = {
        "id": f"{parser}:p{page_index}:b{len(blocks)}",
        "type": str(kind or "unknown"),
        "text": str(text or "").strip(),
        "bbox": box,
        "coordinate_system": "top-left",
        "confidence": None,
        "level": level,
    }
    if polygon:
        block["polygon"] = polygon
    if source_id is not None:
        block["source_id"] = str(source_id)
    blocks.append(block)


def plain_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(filter(None, (plain_text(item) for item in value)))
    if isinstance(value, dict):
        return plain_text(value.get("content") or value.get("text") or "")
    return ""


def html_text(value: str) -> str:
    return unescape(re.sub(r"<[^>]+>", " ", value or "")).strip()


def model_to_plain(value):
    """Avoid Marker/Pydantic's broken model_dump() on some nested JSON outputs."""
    from pydantic import BaseModel

    if isinstance(value, BaseModel):
        return {key: model_to_plain(item) for key, item in vars(value).items()}
    if isinstance(value, dict):
        return {str(key): model_to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [model_to_plain(item) for item in value]
    return value


def run_pymupdf(pdf_path: Path, pages: list[dict]) -> dict:
    import pymupdf as fitz

    raw = {"pages": []}
    with fitz.open(pdf_path) as pdf:
        for i, page in enumerate(pdf):
            blocks = page.get_text("blocks", flags=fitz.TEXTFLAGS_BLOCKS | fitz.TEXT_PRESERVE_IMAGES)
            raw["pages"].append({"page_index": i, "blocks": blocks})
            for item in blocks:
                # PyMuPDF text coordinates are unrotated; turn them into displayed page coordinates.
                rect = fitz.Rect(item[:4]) * page.rotation_matrix
                add_block(pages, "pymupdf", i, "text" if item[6] == 0 else "image", item[4], tuple(rect))
    return raw


def run_docling(pdf_path: Path, pages: list[dict]) -> dict:
    from docling.document_converter import DocumentConverter

    raw = DocumentConverter().convert(str(pdf_path)).document.export_to_dict()
    for collection in ("texts", "tables", "pictures", "key_value_items", "form_items"):
        for item in raw.get(collection, []):
            for prov in item.get("prov", []):
                i = prov.get("page_no", 0) - 1
                if not 0 <= i < len(pages):
                    continue
                box = prov.get("bbox") or {}
                coords = [box.get(k) for k in ("l", "t", "r", "b")]
                if box.get("coord_origin", "TOPLEFT") == "BOTTOMLEFT" and None not in coords:
                    h = pages[i]["height"]
                    coords = [coords[0], h - coords[1], coords[2], h - coords[3]]
                add_block(pages, "docling", i, item.get("label", collection),
                          item.get("text") or item.get("caption") or "", coords,
                          source_id=item.get("self_ref"))
    return raw


def run_mineru(pdf_path: Path, pages: list[dict]) -> dict:
    from mineru.parser import parse

    raw = parse(str(pdf_path), tier="flash").to_dict()
    normalize_mineru_raw(raw, pages)
    return raw


def normalize_mineru_raw(raw: dict, pages: list[dict]) -> None:
    if raw.get("schema") != "docvortex.middle":
        raise ValueError("MinerU 输出不是新版 Middle JSON (docvortex.middle)")
    for page in raw.get("pages", []):
        i = page.get("page_idx")
        if not isinstance(i, int) or not 0 <= i < len(pages):
            continue
        width, height = pages[i]["width"], pages[i]["height"]
        for block in page.get("blocks", []):
            box = block.get("bbox")
            # MinerU 4.1 emits page fractions (0..1); some older outputs use 0..1000.
            if isinstance(box, list) and len(box) == 4:
                scale = 1 if max(box) <= 1 else 1000
                box = [box[0] * width / scale, box[1] * height / scale,
                       box[2] * width / scale, box[3] * height / scale]
            add_block(pages, "mineru", i, block.get("type"), plain_text(block.get("content")), box,
                      source_id=block.get("index"))


def run_marker(pdf_path: Path, pages: list[dict]) -> dict:
    from marker.config.parser import ConfigParser
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict

    config = ConfigParser({"output_format": "json", "disable_ocr": True, "mode": "fast"})
    converter = PdfConverter(
        config=config.generate_config_dict(), artifact_dict=create_model_dict(),
        processor_list=config.get_processors(), renderer=config.get_renderer(),
        llm_service=config.get_llm_service(),
    )
    raw = model_to_plain(converter(str(pdf_path)))
    for page_index, page in enumerate(raw.get("children", [])):
        if page_index >= len(pages):
            break

        def walk(children, level):
            for child in children or []:
                kind = child.get("block_type", "unknown")
                if kind not in ("Page", "Document"):
                    add_block(pages, "marker", page_index, kind, html_text(child.get("html", "")),
                              child.get("bbox"), polygon=child.get("polygon"), level=level,
                              source_id=child.get("id"))
                walk(child.get("children"), "line" if level == "block" else "span")

        walk(page.get("children"), "block")
    return raw


def run_unstructured(pdf_path: Path, pages: list[dict]) -> dict:
    from unstructured.partition.pdf import partition_pdf

    elements = partition_pdf(filename=str(pdf_path), strategy="fast")
    raw = {"elements": [element.to_dict() for element in elements]}
    for element in raw["elements"]:
        meta = element.get("metadata") or {}
        page_no = meta.get("page_number")
        if not isinstance(page_no, int) or not 1 <= page_no <= len(pages):
            continue
        coords = meta.get("coordinates") or {}
        points = coords.get("points") or []
        if not points:
            continue
        i = page_no - 1
        system = coords.get("system")
        source_width = coords.get("layout_width") or pages[i]["width"]
        source_height = coords.get("layout_height") or pages[i]["height"]
        xs = [point[0] * pages[i]["width"] / source_width for point in points]
        ys = [point[1] * pages[i]["height"] / source_height for point in points]
        if system in ("PointSpace", "RelativeCoordinateSystem"):
            ys = [pages[i]["height"] - y for y in ys]
        add_block(pages, "unstructured", i, element.get("type"), element.get("text"),
                  [min(xs), min(ys), max(xs), max(ys)], source_id=element.get("element_id"))
    return raw


RUNNERS = {
    "pymupdf": run_pymupdf,
    "docling": run_docling,
    "mineru": run_mineru,
    "marker": run_marker,
    "unstructured": run_unstructured,
}


def parse(pdf_path: Path, parser: str) -> tuple[dict, list[dict]]:
    pages = empty_pages(page_sizes(pdf_path))
    return RUNNERS[parser](pdf_path, pages), pages
