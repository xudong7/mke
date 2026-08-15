# backend/runs.py
"""运行历史持久化：每次流水线执行为一个 run，JSON 文件存于 data/runs/<run_id>.json。

前端在流水线开始前创建 run，每个步骤完成后 PUT 更新该步骤结果
（extract/cite/structurize 成功时把 records 镜像持久化），
刷新/跳转后可随时从历史恢复完整看板状态，零 LLM 重跑。
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import deps

router = APIRouter(prefix="/runs", tags=["runs"])

_lock = threading.Lock()

STEP_IDS = ("parse", "route", "extract", "cite", "structurize")
# 成功时会把 payload 镜像到 run["records"] 的步骤
RECORD_STEPS = ("extract", "cite", "structurize")


class RunCreate(BaseModel):
    paper_id: str


class StepUpdate(BaseModel):
    status: str  # pending | running | done | error | skipped
    payload: object | None = None
    took_ms: int | None = None
    warning: str | None = None


def _file_for(run_id: str) -> Path:
    return deps.RUNS_DIR / f"{run_id}.json"


def _read(run_id: str) -> dict | None:
    f = _file_for(run_id)
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _write(run: dict) -> None:
    deps.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    _file_for(run["id"]).write_text(
        json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _new_step() -> dict:
    return {"status": "pending", "payload": None, "took_ms": None, "warning": None}


def _derive_status(run: dict) -> str:
    statuses = {run["steps"][s]["status"] for s in STEP_IDS}
    if "error" in statuses:
        return "failed"
    if statuses == {"done"}:
        return "done"
    return "running"


def summary(run: dict) -> dict:
    """摘要（列表用，不含 payload，避免大响应）。"""
    return {
        "id": run["id"],
        "paper_id": run["paper_id"],
        "created_at": run["created_at"],
        "updated_at": run["updated_at"],
        "status": run["status"],
        "record_count": len(run.get("records", [])),
        "step_statuses": {s: run["steps"][s]["status"] for s in STEP_IDS},
    }


def _read_or_404(run_id: str) -> dict:
    run = _read(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"运行记录不存在: {run_id}")
    return run


@router.post("", status_code=201)
def create_run(body: RunCreate):
    """创建一次运行（状态 running，所有步骤 pending）。"""
    # 校验论文存在（复用 papers 的查找逻辑）
    from .papers import _find_paper

    _find_paper(body.paper_id)  # 404 时抛出

    run = {
        "id": uuid.uuid4().hex,
        "paper_id": body.paper_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "steps": {s: _new_step() for s in STEP_IDS},
        "records": [],
    }
    with _lock:
        _write(run)
    return summary(run)


@router.put("/{run_id}/steps/{step}")
def update_step(run_id: str, step: str, body: StepUpdate):
    """更新某步骤结果；extract/cite/structurize 成功时镜像 records。"""
    if step not in STEP_IDS:
        raise HTTPException(status_code=422, detail=f"未知步骤: {step}")
    if body.status not in ("pending", "running", "done", "error", "skipped"):
        raise HTTPException(status_code=422, detail=f"未知状态: {body.status}")

    with _lock:
        run = _read_or_404(run_id)
        run["steps"][step] = {
            "status": body.status,
            "payload": body.payload,
            "took_ms": body.took_ms,
            "warning": body.warning,
        }
        if step in RECORD_STEPS and body.status == "done" and isinstance(body.payload, list):
            run["records"] = body.payload
        run["status"] = _derive_status(run)
        run["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write(run)
    return summary(run)


@router.get("/{run_id}")
def get_run(run_id: str):
    """完整 run（含各步 payload 与 records），用于恢复看板状态。"""
    return _read_or_404(run_id)


# ---- 按论文查运行历史（独立前缀，单独挂载） ----
papers_runs_router = APIRouter(tags=["runs"])


@papers_runs_router.get("/papers/{paper_id}/runs")
def list_paper_runs(paper_id: str):
    """该论文的全部运行记录摘要，按创建时间倒序。"""
    if not deps.RUNS_DIR.is_dir():
        return []
    items = []
    for f in deps.RUNS_DIR.glob("*.json"):
        try:
            run = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if run.get("paper_id") == paper_id:
            items.append(summary(run))
    items.sort(key=lambda r: r["created_at"], reverse=True)
    return items
