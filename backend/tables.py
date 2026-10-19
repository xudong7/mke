# backend/tables.py
"""PDF 表格抽取：多引擎并集 PyMuPDF 版面模型 + 基础 lines + pdfplumber。

引擎都是可选依赖，缺哪个就自动跳过；每路候选返回统一的 TableBlock
（原始 bbox + GFM markdown），按页合并去重后供 parser.py 在正文中原位插入。

选型背景见 memory「P0-1 表格选型」：同一批语料上基础 PyMuPDF find_tables
基本抽不到（三线表无框线），pdfplumber 双栏漏检多，PyMuPDF 版面模型召回最高。

抽出的"表"要过一道误检闸（_looks_like_table），滤掉三类明显不是表的块：
1) 形状不成表（<2 行或 <2 列）；
2) 纯文本无数字（作者行、期刊元信息等）；
3) 首页顶部抬头区（文章历史 / 收稿日期 / 版权声明）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

# ---- 误检闸阈值（可按需调整）----
_MIN_ROWS = 2
_MIN_COLS = 2
_HEADER_ZONE = 0.10              # 任意页：表格顶部落在页面上 10% → 跑页眉
_FOOTER_ZONE = 0.88             # 任意页：表格顶部落在页面下 12% → 跑页脚
_FIRST_PAGE_HEADER_ZONE = 0.15   # 首页顶部 15% 视为期刊抬头区
_PROSE_MIN_AVG_LEN = 30          # 平均格长超过此值且数字极少 → 判为段落
_PROSE_MAX_NUMERIC_RATIO = 0.10
_MIN_FILLED_PER_ROW = 1.5        # 平均每行非空格子数下限（散文块通常只有 1 个格子有字）
_ZONE_MAX_ROWS = 2               # 页眉/页脚区闸只作用于 ≤2 行的小表


@dataclass
class TableBlock:
    page: int
    bbox: tuple[float, float, float, float]
    n_rows: int
    n_cols: int
    markdown: str


def _layout_activate() -> bool:
    """激活 PyMuPDF 版面模型（全局生效，幂等）。没装 pymupdf-layout 时返回 False。"""
    try:
        import pymupdf.layout
        pymupdf.layout.activate()
        return True
    except Exception:
        return False


def _cells(table) -> list:
    try:
        return table.extract() or []
    except Exception:
        return []


def _looks_like_table(
    rows: list,
    page_no: int,
    page_height: float,
    bbox: tuple[float, float, float, float],
) -> bool:
    """误检闸：判断这块“表”是否像真的表格。"""
    if not rows:
        return False

    n_rows = len(rows)
    n_cols = max((len(r) for r in rows), default=0)

    texts = [str(c).strip() for r in rows for c in r if c is not None and str(c).strip()]
    if not texts:
        return False

    # 强放行：首格以 "Table N" 开头 → 就是带表题的真表（即使列没分对/被压成单列也放行）
    if re.match(r"(?i)table\s*\d", texts[0]):
        return True

    if n_cols < _MIN_COLS or n_rows < _MIN_ROWS:
        return False

    numeric = sum(1 for t in texts if any(ch.isdigit() for ch in t))
    if numeric == 0:  # 纯文本无数字 → 假表
        return False

    avg_len = sum(len(t) for t in texts) / len(texts)
    numeric_ratio = numeric / len(texts)
    if numeric_ratio < _PROSE_MAX_NUMERIC_RATIO and avg_len > _PROSE_MIN_AVG_LEN:
        return False  # 长句为主、几乎没有数字 → 段落

    # 真·多列：散文块通常整行只有 1 个格子有字
    filled = sum(1 for r in rows for c in r if c is not None and str(c).strip())
    if filled / len(rows) < _MIN_FILLED_PER_ROW:
        return False

    # 页眉/页脚区（任意页）：只对“小表”（薄条）生效——跑页眉/页码通常是 1–2 行；
    # 大表即便排在页顶也多是正文真表，不能因位置误删。
    y0 = bbox[1]
    if n_rows <= _ZONE_MAX_ROWS:
        if y0 < _HEADER_ZONE * page_height or y0 > _FOOTER_ZONE * page_height:
            return False
        if page_no == 1 and y0 < _FIRST_PAGE_HEADER_ZONE * page_height:
            return False  # 首页顶部：期刊抬头

    return True


def _rows_to_gfm(rows: list) -> str:
    """二维单元格列表 → GFM 表格。第一行当表头。"""
    if not rows:
        return ""

    def cell(c) -> str:
        if c is None:
            return ""
        return str(c).replace("\n", " ").replace("|", "\\|").strip()

    ncol = max((len(r) for r in rows), default=0)
    if ncol == 0:
        return ""

    lines = []
    for i, r in enumerate(rows):
        cells = [cell(r[j]) if j < len(r) else "" for j in range(ncol)]
        lines.append("| " + " | ".join(cells) + " |")
        if i == 0:
            lines.append("|" + "|".join(["---"] * ncol) + "|")
    return "\n".join(lines)


def _norm_cell(c) -> str:
    return re.sub(r"\s+", "", str(c).lower()) if c is not None else ""


def _drop_dup_header(rows: list) -> list:
    """首行与次行内容几乎相同 → 丢掉首行。

    版面模型常把表题、或重复的表头写成第一行（样例：介孔文献78 的 Table 2，
    首行是 “Cr-TiO2 samples. Sample|Band edge…”，次行才是真表头）。
    """
    if len(rows) < 3:
        return rows
    a = [_norm_cell(c) for c in rows[0]]
    b = [_norm_cell(c) for c in rows[1]]
    nc = max(len(a), len(b))
    if nc == 0:
        return rows
    same = sum(
        1
        for i in range(nc)
        if (a[i] if i < len(a) else "") == (b[i] if i < len(b) else "")
        and (a[i] if i < len(a) else "") != ""
    )
    if same >= max(2, nc // 2 + 1):
        return rows[1:]
    return rows


def _strip_md_dup_header(md: str) -> str:
    """GFM 里首行(表头)与第三行几乎相同 → 首行是表题/重复表头串行，去掉它。

    to_markdown() 有时把表题当成表头塞进第一行（样例：介孔文献78 的 Table 2，
    首行 “Cr-TiO2 samples. Sample|Band edge…”，第三行才是真表头）。
    """
    lines = md.split("\n")
    if len(lines) < 3 or set(lines[1].replace(" ", "")) - set("-|"):
        return md
    h = [_norm_cell(c) for c in lines[0].strip("|").split("|")]
    nxt = [_norm_cell(c) for c in lines[2].strip("|").split("|")]
    nc = max(len(h), len(nxt))
    same = sum(1 for i in range(nc) if h[i] and i < len(nxt) and h[i] == nxt[i])
    if nc and same >= max(2, nc // 2 + 1):
        return "\n".join([lines[2], lines[1]] + lines[3:])
    return md


def _to_block(page_no: int, page_height: float, table) -> TableBlock | None:
    """表格对象 → TableBlock；未通过误检闸返回 None。"""
    rows = _cells(table)
    bbox = tuple(float(v) for v in table.bbox)
    if not _looks_like_table(rows, page_no, page_height, bbox):
        return None

    # 用 to_markdown() 保数值保真（extract() 拼接 PDF span 有损，会把 2.47 拼成 “247 .”）；
    # 表题/重复表头串行再在 markdown 层剥掉。
    try:
        md = table.to_markdown()
    except Exception:
        md = _rows_to_gfm(rows)
    if not md:
        md = _rows_to_gfm(rows)
    md = _strip_md_dup_header(md)
    if not md:
        return None

    n_rows = len(md.split("\n")) - 1
    n_cols = int(getattr(table, "col_count", 0)) or max((len(r) for r in rows), default=0)
    return TableBlock(page_no, bbox, n_rows, n_cols, md)


def _collect_pymupdf(pdf_path: Path, strategy: str | None = None) -> dict[int, list[TableBlock]]:
    """用 pymupdf 收候选表。strategy=None 走当前生效策略（激活版面模型则走版面模型）。"""
    out: dict[int, list[TableBlock]] = {}
    doc = pymupdf.open(pdf_path)
    try:
        for pno, page in enumerate(doc, start=1):
            try:
                ft = page.find_tables(strategy=strategy) if strategy else page.find_tables()
                tabs = list(ft.tables)
            except Exception:
                tabs = []
            blocks = [b for b in (_to_block(pno, page.rect.height, t) for t in tabs) if b]
            if blocks:
                out[pno] = blocks
    finally:
        doc.close()
    return out


def _collect_pdfplumber(pdf_path: Path) -> dict[int, list[TableBlock]]:
    import pdfplumber

    out: dict[int, list[TableBlock]] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            try:
                tabs = page.find_tables()
            except Exception:
                tabs = []
            blocks = []
            for t in tabs:
                rows = _cells(t)
                bbox = tuple(float(v) for v in t.bbox)
                if not _looks_like_table(rows, pno, page.height, bbox):
                    continue
                clean = _drop_dup_header(rows)
                md = _rows_to_gfm(clean)
                if not md:
                    continue
                ncol = max((len(r) for r in clean), default=0)
                blocks.append(TableBlock(pno, bbox, len(clean), ncol, md))
            if blocks:
                out[pno] = blocks
    return out


def _iou(a: tuple, b: tuple) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


_IOU_DEDUP = 0.30  # 两个候选 bbox 重叠超此值视为同一张表


def _dedupe(blocks: list[TableBlock]) -> list[TableBlock]:
    """同一页多引擎命中同一张表时去重：格子多的优先留；再按纵向位置排序。"""
    kept: list[TableBlock] = []
    for b in sorted(blocks, key=lambda x: x.n_rows * x.n_cols, reverse=True):
        if any(_iou(b.bbox, k.bbox) > _IOU_DEDUP for k in kept):
            continue
        kept.append(b)
    return sorted(kept, key=lambda x: x.bbox[1])


def extract_tables(pdf_path: str | Path) -> dict:
    """多引擎并集抽表：版面模型 + 基础 lines + pdfplumber。

    三路候选按页合并，再按 bbox 重叠去重（格子多者优先），统一过误检闸。
    早期实现是“按篇先到先得”，版面模型一旦有产出就独占，导致它在个别页
    漏检时其它引擎无法补位（样例：介孔文献12/11 的 Table 3）；并集可补回。

    返回 {"engine": "union(...)", "by_page": {page_no: [TableBlock, ...]}}。
    """
    pdf_path = Path(pdf_path)

    sources: list[tuple[str, dict[int, list[TableBlock]]]] = []
    # 基础 lines 必须在激活版面模型之前收：activate() 是进程级全局的，
    # 激活后再传 strategy="lines" 也会被版面模型接管，拿不到基础结果。
    sources.append(("base-lines", _collect_pymupdf(pdf_path, "lines")))
    try:
        sources.append(("plumber", _collect_pdfplumber(pdf_path)))
    except Exception:
        pass
    if _layout_activate():
        sources.append(("layout", _collect_pymupdf(pdf_path, None)))

    pages: set[int] = set()
    for _, d in sources:
        pages |= set(d)

    by_page: dict[int, list[TableBlock]] = {}
    for pno in pages:
        cands: list[TableBlock] = []
        for _, d in sources:
            cands.extend(d.get(pno, []))
        kept = _dedupe(cands)
        if kept:
            by_page[pno] = kept

    engine = "union(" + "+".join(n for n, _ in sources) + ")"
    return {"engine": engine, "by_page": by_page}
