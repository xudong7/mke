# scripts/parse_corpus.py
"""批量解析语料 PDF → data/parsed/<paper_id>/{content.md, tables/*.md, parse_report.json}。

用法（在项目根目录执行）:
  uv run python scripts/parse_corpus.py                 # 默认 100文献 → data/parsed
  uv run python scripts/parse_corpus.py --limit 5       # 只跑前 5 篇（快速验收）
  uv run python scripts/parse_corpus.py --name 文献12    # 只跑文件名含“文献12”的
  uv run python scripts/parse_corpus.py --ids 介孔文献85,介孔文献12   # 只跑指定几篇
  uv run python scripts/parse_corpus.py --in <dir> --out <dir>

输出末尾有一张「正文 Table 标题数 vs 实际抽出的表格数」对照表，用于粗判召回。
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.parser import parse_pdf  # noqa: E402

DEFAULT_IN = Path(r"C:\Users\29077\Desktop\文献\100文献")
DEFAULT_OUT = ROOT / "data" / "parsed"


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="indir", type=Path, default=DEFAULT_IN)
    ap.add_argument("--out", dest="outdir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--name", default="", help="只解析文件名含该子串的 PDF")
    ap.add_argument("--ids", default="", help="逗号分隔的论文名（精确匹配文件名，不含扩展名），只解析这些")
    args = ap.parse_args()

    pdfs = sorted(args.indir.glob("*.pdf"))
    if args.name:
        pdfs = [p for p in pdfs if args.name in p.name]
    if args.ids:
        want = {s.strip() for s in args.ids.split(",") if s.strip()}
        pdfs = [p for p in pdfs if p.stem in want]
    if args.limit:
        pdfs = pdfs[: args.limit]
    if not pdfs:
        print(f"没找到 PDF: {args.indir}")
        return

    args.outdir.mkdir(parents=True, exist_ok=True)

    print(f"{'paper':<14}{'caps':>5}{'tables':>8}{'rows':>6}{'pages':>7}  engine")
    print("-" * 64)
    n_tables = n_rows = n_caps = 0
    for pdf in pdfs:
        paper_id = pdf.stem
        try:
            r = parse_pdf(pdf)
        except Exception as e:  # 单篇失败不影响全批
            print(f"{paper_id:<14}  ERROR: {e}", flush=True)
            continue

        meta = r["meta"]
        caps = len(set(re.findall(r"Table\s*(\d+)", r["markdown"])))
        tables = r.get("tables", [])
        rows = sum(t["n_rows"] for t in tables)

        out_paper = args.outdir / paper_id
        (out_paper / "tables").mkdir(parents=True, exist_ok=True)
        for old in (out_paper / "tables").glob("*.md"):  # 清掉上次的陈旧表，避免堆积
            old.unlink()
        (out_paper / "content.md").write_text(r["markdown"], encoding="utf-8")
        for ti, t in enumerate(tables, 1):
            (out_paper / "tables" / f"table_{ti}.md").write_text(t["markdown"], encoding="utf-8")

        report = {
            "paper_id": paper_id,
            "page_count": meta["page_count"],
            "column_stats": r["column_stats"],
            "table_engine": meta["table_engine"],
            "table_count": len(tables),
            "table_row_total": rows,
            "table_captions_in_text": caps,
            "char_count": meta["char_count"],
            "section_count": r["section_count"],
            "header_footer_filtered_count": r["header_footer_filtered_count"],
            "tables": [
                {"index": ti, "page": t["page"], "n_rows": t["n_rows"], "n_cols": t["n_cols"]}
                for ti, t in enumerate(tables, 1)
            ],
        }
        (out_paper / "parse_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        print(f"{paper_id:<14}{caps:>5}{len(tables):>8}{rows:>6}{meta['page_count']:>7}  {meta['table_engine']}", flush=True)
        n_tables += len(tables)
        n_rows += rows
        n_caps += caps

    print("-" * 64)
    print(f"共 {len(pdfs)} 篇：抽出表格 {n_tables} 张 / 行 {n_rows}，正文 Table 标题合计 {n_caps} 个")
    print(f"输出目录: {args.outdir}")


if __name__ == "__main__":
    main()
