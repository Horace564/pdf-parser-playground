"""Run with: uvicorn main:app --reload (from backend/)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from parsers import PARSERS, installed, normalize_mineru_raw, parse


ROOT = Path(__file__).resolve().parent / "storage"
ROOT.mkdir(exist_ok=True)

app = FastAPI(title="PDF Parser Playground")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class BlockAction(BaseModel):
    parser: str


def document_dir(document_id: str) -> Path:
    if len(document_id) != 32 or any(c not in "0123456789abcdef" for c in document_id):
        raise HTTPException(404, "Document not found")
    path = ROOT / document_id
    if not (path / "original.pdf").is_file():
        raise HTTPException(404, "Document not found")
    return path


def result_paths(document_id: str, parser: str) -> tuple[Path, Path]:
    if parser not in PARSERS:
        raise HTTPException(400, "Unknown parser")
    folder = document_dir(document_id) / "results" / parser
    return folder / "raw.json", folder / "normalized.json"


@app.get("/parsers")
def list_parsers():
    return [
        {"id": key, "name": name, "installed": installed(key), "package": package}
        for key, (name, package) in PARSERS.items()
    ]


@app.post("/documents")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Please upload a PDF")
    data = await file.read()
    if not data.startswith(b"%PDF-"):
        raise HTTPException(400, "Invalid PDF")
    import pymupdf as fitz

    try:
        with fitz.open(stream=data, filetype="pdf") as pdf:
            if pdf.page_count == 0 or pdf.needs_pass:
                raise ValueError("Empty or encrypted PDF")
            page_count = pdf.page_count
    except Exception as exc:
        raise HTTPException(400, f"Cannot open PDF: {exc}") from exc
    document_id = uuid4().hex
    folder = ROOT / document_id
    folder.mkdir()
    (folder / "original.pdf").write_bytes(data)
    return {"document_id": document_id, "filename": file.filename, "page_count": page_count}


@app.get("/documents/{document_id}/file")
def get_file(document_id: str):
    return FileResponse(document_dir(document_id) / "original.pdf", media_type="application/pdf")


@app.post("/documents/{document_id}/parse")
def parse_document(document_id: str, parser: str = "pymupdf", force: bool = False):
    raw_path, normalized_path = result_paths(document_id, parser)
    if normalized_path.is_file() and not force:
        result = json.loads(normalized_path.read_text(encoding="utf-8"))
        if parser == "mineru" and result.get("normalizer_version") != 2 and raw_path.is_file():
            for page in result["pages"]:
                page["blocks"] = []
            normalize_mineru_raw(json.loads(raw_path.read_text(encoding="utf-8")), result["pages"])
            result["normalizer_version"] = 2
            normalized_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    if not installed(parser):
        raise HTTPException(400, f"{PARSERS[parser][0]} is not installed. Install {PARSERS[parser][1]} first.")
    started = time.perf_counter()
    try:
        raw, pages = parse(document_dir(document_id) / "original.pdf", parser)
    except Exception as exc:
        raise HTTPException(500, f"{parser} parsing failed: {exc}") from exc
    result = {
        "document_id": document_id,
        "parser": parser,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "pages": pages,
        "normalizer_version": 2,
    }
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    normalized_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


@app.get("/documents/{document_id}/results/{parser}/raw")
def get_raw(document_id: str, parser: str):
    raw_path, _ = result_paths(document_id, parser)
    if not raw_path.is_file():
        raise HTTPException(404, "Parse the document first")
    return FileResponse(raw_path, media_type="application/json")


@app.post("/documents/{document_id}/blocks/{block_id}/action")
def block_action(document_id: str, block_id: str, request: BlockAction):
    _, normalized_path = result_paths(document_id, request.parser)
    if not normalized_path.is_file():
        raise HTTPException(404, "Parse the document first")
    result = json.loads(normalized_path.read_text(encoding="utf-8"))
    for page in result["pages"]:
        for block in page["blocks"]:
            if block["id"] == block_id:
                # This is the downstream-task hook: the backend resolves the clicked ID.
                return {
                    "document_id": document_id,
                    "parser": request.parser,
                    "page_index": page["page_index"],
                    "block": block,
                }
    raise HTTPException(404, "Block not found in this parser result")
