# backend/export.py
"""结果导出：Excel（openpyxl，3 表模板格式，从 mke-main server.py 移植）。
- POST /api/export/excel        —— 导出前端当前 records（当前运行）
- GET  /api/runs/{run_id}/export.xlsx —— 导出已持久化的历史 run
两者共用 build_workbook()，把每条记录写成"主表 + 字段引用展开 + 说明"三张表。
"""
from __future__ import annotations

import io
from datetime import datetime
from urllib.parse import quote
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from pydantic import BaseModel

router = APIRouter(prefix="/export", tags=["export"])


class ExportRequest(BaseModel):
    paper_id: str | None = None
    records: list[dict[str, Any]]


# ---- 样式常量（与 mke-main 模板一致） ----
HEADER_FONT = Font(name="Carlito", bold=True, size=11, color="000000")
HEADER_FILL = PatternFill(start_color="EAF3F8", end_color="EAF3F8", fill_type="solid")
THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)

# 主表表头：A 列为文献序号，B..V 对应字段映射列
HEADERS = [
    None,  # A 文献序号
    "记录ID",  # B
    "来源文件",  # C
    "分析类型",  # D
    "组装方式",  # E
    "溶剂体系",  # F
    "pH值_酸碱浓度",  # G
    "表面活性剂种类",  # H
    "表面活性剂浓度",  # I
    "硅/钛源种类_浓度",  # J
    "盐种类_浓度",  # K
    "合成温度",  # L
    "介孔结构",  # M
    "比表面积",  # N
    "孔径",  # O
    "产物形态",  # P
    "其他变量",  # Q
    "组成",  # R
    "结构",  # S
    "来源文本片段",  # T
    "推理说明",  # U
    "字段引用数量",  # V
]
FIELD_MAPPING = {h: h for h in HEADERS[1:]}
COLUMN_WIDTHS = {
    "A": 9.0, "B": 8.0, "C": 23.75, "D": 14.83, "E": 23.0, "F": 18.58,
    "G": 41.08, "H": 26.0, "I": 34.08, "J": 39.58, "K": 8.08, "L": 43.83,
    "M": 32.0, "N": 18.0, "O": 13.0, "P": 32.0, "Q": 38.0, "R": 28.0,
    "S": 13.0, "T": 70.0, "U": 60.0, "V": 14.0,
}

# Sheet3 字段说明图例
FIELD_LEGEND = [
    ("记录ID", "每条抽取记录的唯一标识"),
    ("来源文件", "抽取结果对应的源PDF文件名"),
    ("分析类型", "路由判断的分析深度：软模板法完整分析/仅记录方法等"),
    ("组装方式", "介孔材料的合成方法，如软模板法、硬模板法等"),
    ("溶剂体系", "合成过程中使用的溶剂"),
    ("pH值_酸碱浓度", "反应体系的pH条件或酸碱浓度"),
    ("表面活性剂种类", "使用的表面活性剂类型，如P123、F127等"),
    ("表面活性剂浓度", "表面活性剂的用量或浓度"),
    ("硅/钛源种类_浓度", "硅源或钛源前驱体的种类和用量"),
    ("盐种类_浓度", "添加的盐类及其浓度"),
    ("合成温度", "各步骤的温度条件"),
    ("介孔结构", "介孔结构类型，如二维六方、三维立方等"),
    ("比表面积", "BET比表面积测试结果"),
    ("孔径", "BJH孔径测试结果"),
    ("产物形态", "最终产物的宏观形态"),
    ("其他变量", "其他重要的实验变量或条件"),
    ("组成", "产物的化学组成（适用于复合材料）"),
    ("结构", "产物的结构特征（适用于复合材料）"),
    ("来源文本片段", "支撑抽取结果的原文段落"),
    ("推理说明", "AI推理过程说明"),
    ("字段引用数量", "该记录关联的字段引用条数"),
]


def _normalize_cell_value(value: Any) -> str:
    """把记录字段转成单元格字符串（空→"00"，dict/list 打平）。"""
    if isinstance(value, dict):
        parts = [f"{k}: {v}" for k, v in value.items() if v]
        return ", ".join(parts) if parts else "00"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "00"
    if value is None:
        return "00"
    return str(value)


def build_workbook(records: list[dict[str, Any]], paper_id: str | None = None) -> bytes:
    """按 mke-main 模板生成 3 表 Excel，返回字节。"""
    # 规范化：来源文件缺省用 paper_id，记录ID缺省用序号
    normalized: list[dict[str, Any]] = []
    for i, rec in enumerate(records, 1):
        rec = dict(rec or {})
        if not rec.get("来源文件") and paper_id:
            rec["来源文件"] = paper_id
        rec.setdefault("记录ID", str(i))
        # 字段引用数量（存在则导出）
        cites = rec.get("字段引用") or {}
        if isinstance(cites, dict):
            rec["字段引用数量"] = str(sum(len(v) for v in cites.values() if isinstance(v, list)))
        normalized.append(rec)
    records = normalized

    wb = Workbook()

    # ========== Sheet1: 主表_提取结果 ==========
    ws1 = wb.active
    ws1.title = "主表_提取结果"

    for col, header in enumerate(HEADERS, 1):
        cell = ws1.cell(row=1, column=col, value=header)
        if header:
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = CENTER
            cell.border = THIN_BORDER
    for letter, width in COLUMN_WIDTHS.items():
        ws1.column_dimensions[letter].width = width
    ws1.row_dimensions[1].height = 30

    # 按来源文件分组，同一篇文献共用一个文献编号
    paper_order: list[str] = []
    for rec in records:
        src = rec.get("来源文件") or "未知文献"
        if src not in paper_order:
            paper_order.append(src)
    paper_no = {src: f"文献{i}" for i, src in enumerate(paper_order, 1)}

    row = 2
    for rec in records:
        src = rec.get("来源文件") or "未知文献"

        ws1.row_dimensions[row].height = 58.5
        cell_a = ws1.cell(row=row, column=1, value=paper_no[src])
        cell_a.alignment = CENTER
        cell_a.border = THIN_BORDER

        for col_idx, header in enumerate(HEADERS[1:], 2):  # 从 B 列起
            if header and header in FIELD_MAPPING:
                cell = ws1.cell(row=row, column=col_idx, value=_normalize_cell_value(rec.get(header)))
                cell.border = THIN_BORDER
                cell.alignment = CENTER
        row += 1

        # 备注行（空白，供用户填写批注/修正）
        ws1.row_dimensions[row].height = 22
        note = ws1.cell(row=row, column=1, value="备注")
        note.font = Font(name="Carlito", italic=True, size=10, color="808080")
        note.alignment = CENTER
        note.border = THIN_BORDER
        for _col in range(2, len(HEADERS) + 1):
            ws1.cell(row=row, column=_col).border = THIN_BORDER
        row += 1

    # ========== Sheet2: 字段引用_展开 ==========
    ws2 = wb.create_sheet("字段引用_展开")
    citation_headers = ["记录ID", "来源文件", "字段名", "引用序号", "原文引用"]
    for col, header in enumerate(citation_headers, 1):
        cell = ws2.cell(row=1, column=col, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
        cell.border = THIN_BORDER
    for letter, width in (("A", 10), ("B", 25), ("C", 20), ("D", 10), ("E", 80)):
        ws2.column_dimensions[letter].width = width

    citation_row = 2
    for idx, rec in enumerate(records, 1):
        citations = rec.get("字段引用", {})
        if isinstance(citations, dict):
            for field, sent_list in citations.items():
                if isinstance(sent_list, list):
                    for j, sentence in enumerate(sent_list, 1):
                        values = [idx, rec.get("来源文件", ""), field, j, sentence]
                        for col, v in enumerate(values, 1):
                            cell = ws2.cell(row=citation_row, column=col, value=v)
                            cell.border = THIN_BORDER
                        citation_row += 1
        elif isinstance(citations, list):
            # 兼容旧 list[{field,index,citation}] 格式
            for cite in citations:
                if isinstance(cite, dict):
                    values = [
                        idx,
                        rec.get("来源文件", ""),
                        cite.get("field", ""),
                        cite.get("index", ""),
                        cite.get("citation", ""),
                    ]
                    for col, v in enumerate(values, 1):
                        cell = ws2.cell(row=citation_row, column=col, value=v)
                        cell.border = THIN_BORDER
                    citation_row += 1

    # ========== Sheet3: 说明_查看方法 ==========
    ws3 = wb.create_sheet("说明_查看方法")
    ws3.cell(row=1, column=1, value="字段说明").font = Font(bold=True, size=12)
    for i, (field, desc) in enumerate(FIELD_LEGEND, 3):
        ws3.cell(row=i, column=1, value=field)
        ws3.cell(row=i, column=2, value=desc)
    ws3.column_dimensions["A"].width = 20
    ws3.column_dimensions["B"].width = 60

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()


def _xlsx_response(data: bytes, paper_id: str | None = None) -> StreamingResponse:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = (paper_id or "extraction_result").replace("/", "_")[:40]
    if stem and not stem.isascii():
        # 中文文件名：用 RFC 5987 filename*，另给 ASCII 兜底（header 非 latin-1 会 500）
        encoded = quote(f"extraction_{stem}_{ts}.xlsx")
        disposition = (
            'attachment; filename="extraction_result.xlsx"; '
            f"filename*=UTF-8''{encoded}"
        )
    else:
        disposition = f'attachment; filename="extraction_{stem}_{ts}.xlsx"'
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": disposition},
    )


@router.post("/excel")
def export_excel(body: ExportRequest):
    """导出前端当前 records（当前运行）。"""
    if not body.records:
        raise HTTPException(status_code=400, detail="没有数据可导出")
    try:
        return _xlsx_response(build_workbook(body.records, body.paper_id), body.paper_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {e}")


@router.get("/runs/{run_id}/export.xlsx")
def export_run(run_id: str):
    """导出已持久化的历史 run 的记录。"""
    from .runs import _read_or_404

    run = _read_or_404(run_id)
    records = run.get("records", [])
    if not records:
        raise HTTPException(status_code=400, detail="该运行记录没有可导出的结果（尚未运行完成）")
    try:
        return _xlsx_response(
            build_workbook(records, run.get("paper_id")), run.get("paper_id")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {e}")