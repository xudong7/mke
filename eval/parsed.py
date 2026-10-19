"""eval/parsed.py —— 读取解析线产物 data/parsed/（消费者侧适配层）。

契约见《归档/产物契约_推演草案_2026-10-13.md》第二节：
    data/parsed/<paper_id>/
    ├── content.md          # 正文，含 `<!-- 第 N 页 (X 栏) -->` 与 `<!-- TABLE:table_N -->` 标记
    ├── tables/table_N.md   # 每张表一个文件（GFM 或 HTML）
    └── parse_report.json   # 机器可读的质量报告

解析线还没交付时，本模块不报错，只是报「不可用」，好让评测其余部分照常跑。

用法：
    python -m eval.parsed            # 列出可用论文与汇总
    python -m eval.parsed --check    # 逐篇校验契约，列出问题（有问题退出码 1）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .config import REPO_ROOT

PARSED_DIR = REPO_ROOT / "data" / "parsed"
TABLE_MARK = re.compile(r"<!--\s*TABLE:(table_\d+)\s*-->")


def _paper_number(name: str) -> int | None:
    """目录名归一：paper_10 / 介孔文献10_output / 介孔材料8 → 10 / 10 / 8"""
    m = re.search(r"(\d+)", str(name))
    return int(m.group(1)) if m else None


@dataclass
class ParsedPaper:
    paper_id: int
    dir: Path
    content: str
    report: dict | None = None
    tables: dict[str, str] = field(default_factory=dict)

    @property
    def table_count(self) -> int:
        return len(self.tables)

    @property
    def table_row_count(self) -> int:
        return sum(int(t.get("rows") or 0) for t in (self.report or {}).get("tables", []))

    @property
    def has_sample_column(self) -> bool:
        tabs = (self.report or {}).get("tables", [])
        return any(t.get("sample_column") is not None for t in tabs)


def available_papers() -> dict[int, Path]:
    """扫描 data/parsed/，返回 {文献编号: 目录}。目录名写法随便，编号能解析出来就行。"""
    if not PARSED_DIR.is_dir():
        return {}
    out: dict[int, Path] = {}
    for d in sorted(PARSED_DIR.iterdir()):
        if not d.is_dir():
            continue
        n = _paper_number(d.name)
        if n is not None:
            out[n] = d
    return out


def load(paper_number: int) -> ParsedPaper | None:
    d = available_papers().get(paper_number)
    if d is None:
        return None
    md = d / "content.md"
    content = md.read_text(encoding="utf-8") if md.exists() else ""
    report = None
    rp = d / "parse_report.json"
    if rp.exists():
        try:
            report = json.loads(rp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = None
    tables: dict[str, str] = {}
    tdir = d / "tables"
    if tdir.is_dir():
        for f in sorted(tdir.glob("*.md")):
            tables[f.stem] = f.read_text(encoding="utf-8")
    return ParsedPaper(paper_id=paper_number, dir=d, content=content, report=report, tables=tables)


def violations(p: ParsedPaper) -> list[str]:
    """最小契约校验——只查「融合会不会出错」相关的项，不做格式洁癖。"""
    bad: list[str] = []
    if not p.content.strip():
        bad.append("content.md 缺失或为空")

    if p.report is None:
        bad.append("parse_report.json 缺失或不是合法 JSON")
    else:
        for k in ("paper_id", "page_count", "tables"):
            if k not in p.report:
                bad.append(f"parse_report.json 缺字段 {k}")
        if "parser_version" not in p.report:
            bad.append("parse_report.json 缺 parser_version（跨版本分数将不可比）")

    marks = set(TABLE_MARK.findall(p.content))
    missing_files = sorted(marks - set(p.tables))
    orphan_files = sorted(set(p.tables) - marks)
    if missing_files:
        bad.append(f"正文有标记但缺表格文件：{missing_files}")
    if orphan_files:
        bad.append(f"有表格文件但正文没有对应标记：{orphan_files}")

    tabs = (p.report or {}).get("tables", [])
    if marks and not tabs:
        bad.append("正文有表格标记，但 parse_report.json 的 tables 为空")
    for t in tabs:
        if not t.get("id"):
            bad.append("parse_report.json 的 tables 条目缺 id")
            break
    return bad


def summary() -> dict:
    papers = available_papers()
    loaded = [load(n) for n in sorted(papers)]
    loaded = [p for p in loaded if p]
    return {
        "available": len(loaded),
        "with_tables": sum(1 for p in loaded if p.table_count),
        "tables_total": sum(p.table_count for p in loaded),
        "chars_total": sum(len(p.content) for p in loaded),
        "with_sample_column": sum(1 for p in loaded if p.has_sample_column),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="读取 / 校验解析线产物")
    ap.add_argument("--check", action="store_true", help="逐篇校验契约，有问题退出码 1")
    args = ap.parse_args()

    papers = available_papers()
    if not papers:
        print(f"data/parsed/ 还不存在或为空 → 解析线尚未交付，评测其余部分照常可跑")
        print(f"  期望位置：{PARSED_DIR}")
        sys.exit(0)

    s = summary()
    print(f"可用论文 {s['available']} 篇；含表 {s['with_tables']} 篇 / 表 {s['tables_total']} 张；"
          f"正文合计 {s['chars_total']} 字符；有样品列的表 {s['with_sample_column']} 篇")

    if not args.check:
        for n in sorted(papers):
            p = load(n)
            if p:
                print(f"  文献{n:<4d} 表 {p.table_count:3d}  表行 {p.table_row_count:4d}  正文 {len(p.content):6d} 字符")
        return

    total = 0
    for n in sorted(papers):
        p = load(n)
        if not p:
            continue
        bad = violations(p)
        total += len(bad)
        print(f"[{'OK  ' if not bad else 'BAD '}] 文献{n}")
        for b in bad:
            print(f"        - {b}")
    print(f"\n契约问题合计 {total} 条")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
