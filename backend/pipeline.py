# backend/pipeline.py
"""解析流程分步端点（无状态：前端把上一步结果传入，每步可单独重跑）。

步骤：① parse → ② route → ③ extract → ④ cite → ⑤ structurize
LLM 调用为阻塞式，端点用同步 def（走 FastAPI 线程池，不阻塞事件循环）。
"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.citation_agent import add_field_sentence_citations_for_paper
from core.extractor import MesoporousExtractor
from core.postprocess import simple_format_results
from core.router import route_paper
from core.structurizer_agent import structurize_results

from . import deps
from .parser import parse_pdf

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class ParseRequest(BaseModel):
    paper_id: str


class RouteRequest(BaseModel):
    text: str


class ExtractRequest(BaseModel):
    text: str
    routing: dict


class CiteRequest(BaseModel):
    text: str
    results: list


class StructurizeRequest(BaseModel):
    results: list


def _llm_errors(e: Exception) -> HTTPException:
    if isinstance(e, RuntimeError):
        return HTTPException(status_code=503, detail=str(e))
    return HTTPException(status_code=502, detail=f"LLM 调用失败: {e}")


@router.post("/parse")
def step_parse(body: ParseRequest):
    """① PDF 解析（本地计算，不耗 LLM）：重跑版面重建，返回中间产物。"""
    t0 = time.time()
    for base in (deps.UPLOADS_DIR,):
        pdf_path = base / body.paper_id / "original.pdf"
        if pdf_path.exists():
            try:
                data = parse_pdf(pdf_path)
            except Exception as e:
                raise HTTPException(status_code=422, detail=f"PDF 解析失败: {e}")
            return {"data": data, "took_ms": int((time.time() - t0) * 1000)}
    # corpus 论文无 PDF：走既有 content.md
    md_path = deps.CORPUS_DIR / body.paper_id / "content.md"
    if md_path.exists():
        text = md_path.read_text(encoding="utf-8")
        return {
            "data": {
                "skipped": True,
                "reason": "该论文为语料库既有解析文本（无原始 PDF），跳过版面重建。",
                "markdown": text,
                "meta": {"char_count": len(text)},
            },
            "took_ms": int((time.time() - t0) * 1000),
        }
    raise HTTPException(status_code=404, detail=f"论文不存在或缺少 PDF: {body.paper_id}")


@router.post("/route")
def step_route(body: RouteRequest):
    """② 路由分类：判断软模板/复合结构/硬模板，推荐 skills。"""
    try:
        t0 = time.time()
        data = route_paper(body.text, deps.get_client(), deps.get_model_name())
        return {"data": data, "took_ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        raise _llm_errors(e)


@router.post("/extract")
def step_extract(body: ExtractRequest):
    """③ 主抽取：按路由结果抽取结构化记录，并补全 18 字段 schema。

    注意：simple_format_results 只保留 18 个基础字段，会删除 *_结构化 键，
    因此必须在 structurize（⑤）之前调用且只调用一次。
    """
    try:
        t0 = time.time()
        extractor = MesoporousExtractor(
            api_key=deps.get_client().api_key,
            base_url=deps.get_client().base_url,
            model_name=deps.get_model_name(),
            skill_manager=deps.get_skill_manager(),
        )
        results = extractor.extract_from_text(body.text, routing=body.routing)
        for r in results:
            r.setdefault("来源文件", "")  # 前端会用 paper_id 回填
        # 注：空记录剔除 / 非合成记录过滤 / 重复样品合并，在 extract_from_text
        # 内部按分支完成（简化抽取分支不能按合成条件过滤）。
        results = simple_format_results(results)
        warning = ""
        if not results:
            warning = "未抽取到任何记录，可能为 LLM 解析失败或该文献缺少实验数据。"
        return {
            "data": results,
            "took_ms": int((time.time() - t0) * 1000),
            "warning": warning,
        }
    except Exception as e:
        raise _llm_errors(e)


@router.post("/cite")
def step_cite(body: CiteRequest):
    """④ 字段级整句引用标注：为每条记录的每个字段回找完整英文句子。"""
    try:
        t0 = time.time()
        results = add_field_sentence_citations_for_paper(
            text=body.text,
            structured_results=body.results,
            client=deps.get_client(),
            model_name=deps.get_model_name(),
        )
        return {"data": results, "took_ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        raise _llm_errors(e)


@router.post("/structurize")
def step_structurize(body: StructurizeRequest):
    """⑤ 数值结构化：逐条调用 LLM 拆分 合成温度/比表面积/孔径 为机器可读字段。"""
    try:
        t0 = time.time()
        results = structurize_results(body.results, deps.get_client(), deps.get_model_name())
        return {"data": results, "took_ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        raise _llm_errors(e)
