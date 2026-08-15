# backend/annotations.py
"""结果批注持久化（v2）：批注针对看板抽取结果（run + record + 可选字段），
不影响原结果。每 run 一个 JSON 文件：data/annotations/<run_id>.json。"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import deps

router = APIRouter(tags=["annotations"])

_lock = threading.Lock()


class RunAnnotationIn(BaseModel):
    record_index: int
    field: str | None = None
    note: str = ""
    value_snapshot: str | None = None


class RunAnnotation(RunAnnotationIn):
    id: str
    run_id: str
    paper_id: str
    created_at: str


def _file_for(run_id: str) -> Path:
    return deps.ANNOTATIONS_DIR / f"{run_id}.json"


def _read(run_id: str) -> list[dict]:
    f = _file_for(run_id)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _write(run_id: str, items: list[dict]) -> None:
    deps.ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)
    _file_for(run_id).write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


@router.get("/runs/{run_id}/annotations")
def list_run_annotations(run_id: str):
    return _read(run_id)


@router.post("/runs/{run_id}/annotations", status_code=201)
def create_run_annotation(run_id: str, body: RunAnnotationIn):
    # 校验 run 存在并取其 paper_id（客户端只需提交批注本体）
    from .runs import _read_or_404

    run = _read_or_404(run_id)
    item = {
        "id": uuid.uuid4().hex,
        "run_id": run_id,
        "paper_id": run["paper_id"],
        "record_index": body.record_index,
        "field": body.field,
        "note": body.note,
        "value_snapshot": body.value_snapshot,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        items = _read(run_id)
        items.append(item)
        _write(run_id, items)
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
