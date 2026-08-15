# backend/papers.py
"""论文管理端点：列表 / 全文 / PDF 文件服务 / PDF 上传解析。"""
from __future__ import annotations

import re
import time
import unicodedata
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from . import deps
from .parser import parse_pdf

router = APIRouter(prefix="/papers", tags=["papers"])


def _sanitize_filename(name: str) -> str:
    """保留中文与常规字符，空白 → 下划线，去除危险字符。"""
    name = unicodedata.normalize("NFC", name)
    name = re.sub(r"[^\w一-鿿-]+", "_", name, flags=re.UNICODE)
    return name.strip("_")[:120] or "paper"


def _parse_paper_dir(dir_path: Path, source: str) -> dict:
    """从论文目录解析元信息：目录名形如 'X 等 - YYYY - Title_output'。"""
    name = dir_path.name
    content_md = dir_path / "content.md"
    pdf_file = dir_path / "original.pdf"
    match = re.match(r"^(.*?)\s*等?\s*-\s*(\d{4})\s*-\s*(.+?)(?:_output)?$", name)
    if match:
        first_author, year, title = match.groups()
    else:
        first_author, year, title = name, "", ""
    text_size = content_md.stat().st_size if content_md.exists() else 0
    return {
        "id": name,
        "source": source,
        "title": title.strip(),
        "first_author": first_author.strip(),
        "year": year,
        "text_size": text_size,
        "has_pdf": pdf_file.exists(),
    }


def list_papers() -> list[dict]:
    papers = []
    if deps.CORPUS_DIR.is_dir():
        for d in sorted(deps.CORPUS_DIR.iterdir()):
            if d.is_dir() and (d / "content.md").exists():
                papers.append(_parse_paper_dir(d, "corpus"))
    if deps.UPLOADS_DIR.is_dir():
        for d in sorted(deps.UPLOADS_DIR.iterdir()):
            if d.is_dir() and (d / "content.md").exists():
                papers.append(_parse_paper_dir(d, "upload"))
    return papers


def _find_paper(paper_id: str) -> tuple[Path, str]:
    for base, source in ((deps.CORPUS_DIR, "corpus"), (deps.UPLOADS_DIR, "upload")):
        p = base / paper_id
        if p.is_dir():
            return p, source
    raise HTTPException(status_code=404, detail=f"论文不存在: {paper_id}")


@router.get("")
def papers_list():
    return list_papers()


@router.get("/{paper_id}/text")
def paper_text(paper_id: str):
    p, _ = _find_paper(paper_id)
    md = p / "content.md"
    if not md.exists():
        raise HTTPException(status_code=404, detail="该论文没有解析文本")
    return {"paper_id": paper_id, "text": md.read_text(encoding="utf-8")}


@router.get("/{paper_id}/pdf")
def paper_pdf(paper_id: str):
    p, _ = _find_paper(paper_id)
    pdf = p / "original.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail="该论文没有 PDF 文件")
    return FileResponse(pdf, media_type="application/pdf", filename=f"{paper_id}.pdf")


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """上传 PDF → 版面重建解析 → 存为 content.md，进入论文列表。"""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="请上传 .pdf 文件")

    slug = _sanitize_filename(Path(file.filename).stem)
    paper_dir = deps.UPLOADS_DIR / f"{slug}_output"
    paper_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    pdf_path = paper_dir / "original.pdf"
    pdf_path.write_bytes(await file.read())

    warnings: list[str] = []
    try:
        result = parse_pdf(pdf_path)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"PDF 解析失败（可能为扫描件或无文本层）：{e}")

    if result["meta"]["char_count"] < 200:
        warnings.append("解析出的文本过少，PDF 可能为扫描件（无文本层），抽取效果会受限。")

    (paper_dir / "content.md").write_text(result["markdown"], encoding="utf-8")
    paper_id = paper_dir.name

    return {
        "paper_id": paper_id,
        "has_pdf": True,
        "text": result["markdown"],
        "text_size": len(result["markdown"]),
        "warnings": warnings,
        "parse_meta": {
            "page_count": result["meta"]["page_count"],
            "columns": result["column_stats"],
            "took_ms": int((time.time() - t0) * 1000),
        },
    }
