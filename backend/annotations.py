# backend/annotations.py
"""批注持久化：每篇论文一个 JSON 文件（data/annotations/<paper_id>.json）。"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import deps

router = APIRouter(tags=["annotations"])

_lock = threading.Lock()


class AnchorRect(BaseModel):
    x: float
    y: float
    w: float
    h: float


class Anchor(BaseModel):
    rects: list[AnchorRect] = []
    page_width: float = 0
    page_height: float = 0


class AnnotationIn(BaseModel):
    page: int | None = None
    quote: str = ""
    note: str = ""
    anchor: Anchor = Field(default_factory=Anchor)


class Annotation(AnnotationIn):
    id: str
    paper_id: str
    created_at: str


def _file_for(paper_id: str) -> Path:
    return deps.ANNOTATIONS_DIR / f"{paper_id}.json"


def _read(paper_id: str) -> list[dict]:
    f = _file_for(paper_id)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _write(paper_id: str, items: list[dict]) -> None:
    deps.ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)
    _file_for(paper_id).write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


@router.get("/papers/{paper_id}/annotations")
def list_annotations(paper_id: str):
    return _read(paper_id)


@router.post("/papers/{paper_id}/annotations", status_code=201)
def create_annotation(paper_id: str, body: AnnotationIn):
    item = {
        "id": uuid.uuid4().hex,
        "paper_id": paper_id,
        "page": body.page,
        "quote": body.quote,
        "note": body.note,
        "anchor": body.anchor.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        items = _read(paper_id)
        items.append(item)
        _write(paper_id, items)
    return item


@router.delete("/annotations/{annotation_id}", status_code=204)
def delete_annotation(annotation_id: str):
    for f in deps.ANNOTATIONS_DIR.glob("*.json") if deps.ANNOTATIONS_DIR.is_dir() else []:
        items = json.loads(f.read_text(encoding="utf-8"))
        before = len(items)
        items = [a for a in items if a.get("id") != annotation_id]
        if len(items) != before:
            with _lock:
                _write(f.stem, items)
            return
    raise HTTPException(status_code=404, detail=f"批注不存在: {annotation_id}")
