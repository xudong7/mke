# backend/parser.py
"""PDF 轻量版面重建解析器。

从学术论文 PDF（典型两栏版面）提取结构化 markdown：
- 栏检测：按文本块中心 x 聚类，识别单栏/双栏版面
- 页眉页脚过滤：跨页重复文本（期刊名/卷号）与页码块
- 阅读顺序重建：先按栏（左→右），栏内按 y（上→下）
- 标题检测：字号明显大于正文的块 → markdown 标题
- 段落合并：同栏相邻块合并为段落

纯本地计算（PyMuPDF），无 LLM 调用，秒级完成、幂等。
"""
from __future__ import annotations

import re
import statistics
from pathlib import Path

import pymupdf

from .tables import extract_tables

# 页眉页脚区域占页面高度的比例（顶部/底部各留 10%）
_HEADER_ZONE = 0.10
_FOOTER_ZONE = 0.12
# 跨页重复且长度受限 → 判定为页眉
_MAX_HEADER_LEN = 80
# 字号显著大于正文中位数 → 判定为标题
_TITLE_SIZE_RATIO = 1.35
# 相邻块 y 间距小于该值（相对块高）→ 合并为同一段落
_PARAGRAPH_GAP_RATIO = 0.8
# 栏间最小空隙（相对页面宽度），用于双栏判定
_COLUMN_GAP_RATIO = 0.06

# --- 标题识别（同字号章节标题）---
# 编号式：1 / 2.2 / 3.1.2 后接大写词。PDF 逐词断行会让点号后丢空格，故用 \s*。
_SECTION_RE = re.compile(r"^\d{1,2}(?:\.\d+){0,3}\.?\s*[A-Z][A-Za-z]")
# 深层编号（≥2 级点号）后允许小写开头，如「2.2.1 glypy-Mo(II)」（化合物名常小写）
_DEEP_SECTION_RE = re.compile(r"^\d{1,2}(?:\.\d+){2,}\.?\s*\S")
# 无编号的常见章节名（归一化后去掉空格/尾点号比对）
_SECTION_WORDS = {
    "abstract", "introduction", "experimental", "experimentalsection",
    "conclusion", "conclusions", "discussion", "results", "resultsanddiscussion",
    "acknowledgments", "acknowledgements", "references", "methods",
    "materialsandmethods", "supportinginformation", "supplementaryinformation",
    "appendix", "conclusionsandoutlook",
}
# 页眉/脚注式「假标题」特征，用于排除编号误判
_HEAD_JUNK_RE = re.compile(r"et al\.|doi|@|https?:|www\.|issn", re.IGNORECASE)
# 章节标题的最大归一化长度（超此长度视为正文段落）
_MAX_HEADING_LEN = 90


def _norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _looks_like_heading(text: str, size: float, body_size: float) -> bool:
    """判断文本块是否为标题。

    两条通道：(1) 字号明显大于正文；(2) 同字号但形如编号章节（'2.2. Synthesis'、
    '3. Results and discussion'）或常见章节名（'References'/'Abstract'）——这类在
    正文字号下只能靠文本模式识别，是原逻辑漏检的主要来源。
    """
    t = text.strip()
    if not t or len(t) > 120:
        return False
    if size >= _TITLE_SIZE_RATIO * body_size:      # (1) 大字标题
        return True
    if _HEAD_JUNK_RE.search(t):                    # 页眉/脚注痕迹
        return False
    flat = re.sub(r"\s+", "", t)
    if len(flat) > _MAX_HEADING_LEN:               # (2) 章节标题都很短
        return False
    if _SECTION_RE.match(t) or _DEEP_SECTION_RE.match(t):
        return True
    return flat.lower().rstrip(".:") in _SECTION_WORDS


def _is_page_number(text: str) -> bool:
    """纯页码：如 '601'、'p. 601'、'Page 3 of 12'。"""
    t = _norm_text(text)
    if re.fullmatch(r"\d{1,4}", t):
        return True
    if re.fullmatch(r"(p\.?\s*|page\s*|pp\.?\s*)\d{1,4}", t, re.IGNORECASE):
        return True
    return False


def _detect_columns(blocks: list, page_width: float) -> int:
    """按文本块中心 x 聚类，返回 1 或 2 栏。

    对双栏版面：中心 x 分为左右两个簇，簇间空隙超过阈值。
    """
    centers = sorted(
        (b["x0"] + b["x1"]) / 2 for b in blocks
        if b["text"].strip() and b["x1"] - b["x0"] > 1
    )
    if len(centers) < 4:
        return 1
    # 取中位数左侧与右侧各一半，检查左右半区的中心偏移
    mid = len(centers) // 2
    left_median = statistics.median(centers[:mid])
    right_median = statistics.median(centers[mid:])
    gap = right_median - left_median
    if gap > _COLUMN_GAP_RATIO * page_width:
        return 2
    return 1


def _collect_cross_page_headers(doc) -> set:
    """收集跨 ≥2 页出现且文本相同的块（页眉特征：期刊名/卷号/标题重复）。"""
    from collections import Counter

    counter: Counter = Counter()
    for page in doc:
        seen = set()
        for b in page.get_text("blocks"):
            text = _norm_text(b[4])
            if not text or len(text) > _MAX_HEADER_LEN:
                continue
            if text not in seen:
                seen.add(text)
                counter[text] += 1
    return {t for t, n in counter.items() if n >= 2}


def _lines_to_text(lines: list) -> str:
    """把视觉行拼接为文本；词在行尾被物理断行时补空格。"""
    parts: list[str] = []
    for line in lines:
        t = "".join(s["text"] for s in line.get("spans", []))
        if not t:
            continue
        if parts and parts[-1][-1].isalnum() and t[0].isalnum():
            parts.append(" ")
        parts.append(t)
    return "".join(parts)


def _parse_page(page, page_no: int, page_height: float, page_width: float, headers: set, tables: list | None = None):
    """解析单页：过滤页眉页脚/表格区 → 栏检测 → 阅读顺序排序。"""
    tables = tables or []
    table_rects = [t.bbox for t in tables]
    raw = page.get_text("dict")
    blocks = []
    for b in raw.get("blocks", []):
        if b.get("type") != 0:  # 跳过图片块
            continue
        text = _norm_text(_lines_to_text(b.get("lines", [])))
        if not text:
            continue
        sizes = [s["size"] for line in b.get("lines", []) for s in line.get("spans", []) if s["text"].strip()]
        x0, y0, x1, y1 = b["bbox"]
        # 中心点落在表格 bbox 内的文本块 = 表格内容，剔除以免与表格 markdown 重复
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if any(rx0 <= cx <= rx1 and ry0 <= cy <= ry1 for (rx0, ry0, rx1, ry1) in table_rects):
            continue
        blocks.append({
            "text": text,
            "x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "size": statistics.median(sizes) if sizes else 0,
        })

    filtered, filtered_items = [], []
    for b in blocks:
        text, (x0, y0, x1, y1) = b["text"], (b["x0"], b["y0"], b["x1"], b["y1"])
        # 页眉：跨页重复文本；页脚：底部区域且为页码/短文本
        if text in headers:
            filtered_items.append(("页眉", text))
            continue
        if y0 > _FOOTER_ZONE * page_height and (_is_page_number(text) or len(text) < 24):
            filtered_items.append(("页脚", text))
            continue
        if y1 < _HEADER_ZONE * page_height and _is_page_number(text):
            filtered_items.append(("页眉页码", text))
            continue
        filtered.append(b)

    columns = _detect_columns(filtered, page_width)

    if columns == 2:
        # 按栏分配：中心 x 与左右栏中心比较
        centers = [(b["x0"] + b["x1"]) / 2 for b in filtered]
        mid_x = (max(c for c in centers) + min(c for c in centers)) / 2 if centers else page_width / 2
        ordered = sorted(filtered, key=lambda b: ((b["x0"] + b["x1"]) / 2 > mid_x, b["y0"]))
    else:
        ordered = sorted(filtered, key=lambda b: b["y0"])

    return {
        "page": page_no,
        "columns": columns,
        "filtered_items": filtered_items,
        "blocks": ordered,
        "tables": tables,
    }


def _interleave_tables(blocks: list, tables: list) -> list:
    """把表格按 y0 插入到已排好序的文本块流中，保持块顺序不变。

    返回 [("block", b) | ("table", t), ...]。
    """
    merged: list[tuple[str, object]] = []
    ti = 0
    ordered_tables = sorted(tables, key=lambda t: t.bbox[1])
    for b in blocks:
        while ti < len(ordered_tables) and ordered_tables[ti].bbox[1] <= b["y0"]:
            merged.append(("table", ordered_tables[ti]))
            ti += 1
        merged.append(("block", b))
    while ti < len(ordered_tables):
        merged.append(("table", ordered_tables[ti]))
        ti += 1
    return merged


def _emit_markdown(pages: list, body_size: float) -> str:
    """把排序后的块渲染为 markdown：标题(##) + 段落 + 表格，同栏相邻块合并。"""
    out: list[str] = []
    for p in pages:
        out.append(f"\n\n<!-- 第 {p['page']} 页 ({p['columns']} 栏) -->")
        merged = _interleave_tables(p["blocks"], p.get("tables", []))
        pending: list[str] = []
        pending_y = None
        for kind, item in merged:
            if kind == "table":
                if pending:
                    out.append(" ".join(pending))
                    pending = []
                    pending_y = None
                out.append(item.markdown)
                continue
            b = item
            if _looks_like_heading(b["text"], b["size"], body_size):
                # 标题单独成行；不可并入 pending，否则后续正文会被粘进标题
                if pending:
                    out.append(" ".join(pending))
                    pending = []
                out.append(f"## {b['text']}")
                pending_y = None
                continue
            if pending and pending_y is not None:
                gap = b["y0"] - pending_y
                prev_h = b["y1"] - b["y0"]
                if gap <= max(_PARAGRAPH_GAP_RATIO * prev_h, 6):
                    pending.append(b["text"])
                    pending_y = b["y1"]
                    continue
            if pending:
                out.append(" ".join(pending))
            pending = [b["text"]]
            pending_y = b["y1"]
        if pending:
            out.append(" ".join(pending))
    return "\n\n".join(out)


def parse_pdf(pdf_path: str | Path) -> dict:
    """解析 PDF，返回版面分析中间产物 + markdown 全文。"""
    pdf_path = Path(pdf_path)

    table_info = extract_tables(pdf_path)
    by_page = table_info["by_page"]

    doc = pymupdf.open(pdf_path)
    try:
        headers = _collect_cross_page_headers(doc)
        pages = []
        body_sizes = []
        for pno, page in enumerate(doc, start=1):
            rect = page.rect
            parsed = _parse_page(page, pno, rect.height, rect.width, headers, by_page.get(pno, []))
            pages.append(parsed)
            for b in parsed["blocks"]:
                body_sizes.append(b["size"])

        body_size = statistics.median(body_sizes) if body_sizes else 10.0
        markdown = _emit_markdown(pages, body_size)

        single_col = sum(1 for p in pages if p["columns"] == 1)
        double_col = sum(1 for p in pages if p["columns"] == 2)
        section_count = markdown.count("\n## ")
        total_filtered = sum(len(p["filtered_items"]) for p in pages)

        tables = [
            {
                "page": t.page,
                "n_rows": t.n_rows,
                "n_cols": t.n_cols,
                "markdown": t.markdown,
            }
            for p in pages
            for t in p.get("tables", [])
        ]

        return {
            "pages": [
                {
                    "page": p["page"],
                    "columns": p["columns"],
                    "filtered": p["filtered_items"],
                    "blocks_kept": len(p["blocks"]),
                    "tables": len(p.get("tables", [])),
                }
                for p in pages
            ],
            "column_stats": {"single": single_col, "double": double_col},
            "header_footer_filtered_count": total_filtered,
            "section_count": section_count,
            "markdown": markdown,
            "tables": tables,
            "meta": {
                "page_count": len(pages),
                "char_count": len(markdown),
                "body_size_pt": round(body_size, 1),
                "header_texts": sorted(headers),
                "table_engine": table_info["engine"],
                "table_count": len(tables),
                "table_row_total": sum(t["n_rows"] for t in tables),
            },
        }
    finally:
        doc.close()
