"""eval/golden.py —— 人工标注 .xls → eval/data/golden.jsonl

行型规则（实测，详见 eval/DESIGN.md 2.1）：
  「文献N」行   → 一条记录
  首列为空的行  → 同篇论文的追加样品，也是记录（仅 sheet「文献1-7」出现 31 行）
  「备注」/「计算过程」行 → 上一条记录的注释，不是记录
  全空杂行（首列只有编号、其余全空）→ 丢弃

用法：python -m eval.golden
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from .config import DATA_DIR, REPO_ROOT, fields, schema_version

SRC_XLS = REPO_ROOT.parent / "文献1-100提取标准结果及其解析.xls"
OUT_JSONL = DATA_DIR / "golden.jsonl"

NOTE_LABELS = {"备注", "计算过程"}
# 已定稿的排除项（DESIGN 2.2）：有 gold 标注但没有 PDF，评测分母按 97 篇 / 261 条算。
# 保留 --keep-excluded 开关，将来补到 PDF 可以随时启用。
EXCLUDED_PAPERS = {32, 36, 46}
# 行型统计的期望值（DESIGN 2.1）；对不上就打警告，不静默通过
EXPECT_RECORDS = 264
EXPECT_PAPERS = 100


def _fmt_number(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(x)


def _clean(v) -> str | None:
    """归一单格：数值去尾零、文本去空白；空 / — / null / 00 统一为 None。"""
    if v is None:
        return None
    if isinstance(v, float):
        return _fmt_number(v)
    s = str(v).replace("\u00a0", " ").strip()
    if s == "" or s.lower() in {"—", "-", "–", "－", "null", "00", "none", "n/a"}:
        return None
    return s


def _join_note(cells: list) -> str | None:
    parts = [str(c).strip().replace("\n", " ") for c in cells if str(c).strip()]
    return " | ".join(parts) if parts else None


def read_golden_xls(path: Path) -> tuple[list[dict], dict]:
    import xlrd

    book = xlrd.open_workbook(str(path))
    keys = [f["key"] for f in fields()]
    if len(keys) != 14:
        raise SystemExit(f"schema.yaml 的字段数应为 14，实际 {len(keys)}")

    records: list[dict] = []
    stat = Counter()

    for sheet_name in book.sheet_names():
        sheet = book.sheet_by_name(sheet_name)
        header = [str(c.value).strip() for c in sheet.row(0)]
        if header[0] != "文献编号":
            raise SystemExit(f"{sheet_name}: 表头与预期不符 → {header[:3]}")
        current_paper: str | None = None

        for r in range(1, sheet.nrows):
            raw = [sheet.cell_value(r, c) for c in range(sheet.ncols)]
            label = str(raw[0]).strip()
            values = [_clean(v) for v in raw[1:]]

            if label == "" and all(v is None for v in values):
                stat["空行(丢弃)"] += 1
                continue

            if label.startswith("文献"):
                if all(v is None for v in values):
                    stat["全空杂行(丢弃)"] += 1
                    continue
                current_paper = label
                stat["编号行"] += 1
            elif label == "":
                if current_paper is None:
                    raise SystemExit(f"{sheet_name} r{r + 1}: 续行出现在任何记录之前")
                stat["续行"] += 1
            elif label in NOTE_LABELS:
                stat[f"注释行:{label}"] += 1
                if not records:
                    raise SystemExit(f"{sheet_name} r{r + 1}: 注释行之前没有记录")
                note = _join_note(raw[1:])
                if note:
                    prev = records[-1]
                    prev["note"] = f"{prev['note']} | {note}" if prev.get("note") else note
                continue
            else:
                stat[f"未知行型:{label[:8]}"] += 1
                continue

            if label.startswith("文献"):
                current_paper = label

            paper_label = current_paper
            m = re.search(r"(\d+)", paper_label or "")
            if not m:
                raise SystemExit(f"{sheet_name} r{r + 1}: 无法从 {paper_label!r} 解析文献编号")

            records.append(
                {
                    "paper_id": int(m.group(1)),
                    "paper_label": paper_label,
                    "record_index": 0,  # 下面按论文重排
                    "global_index": len(records) + 1,
                    "source": {"sheet": sheet_name, "row": r + 1},
                    "fields": {k: v for k, v in zip(keys[1:13], values[:12])},
                    "note": None,
                }
            )

    # 记录序号：按论文内出现顺序
    per_paper: Counter = Counter()
    for rec in records:
        per_paper[rec["paper_id"]] += 1
        rec["record_index"] = per_paper[rec["paper_id"]]

    stat["记录合计"] = len(records)
    stat["覆盖论文数"] = len(per_paper)
    return records, dict(stat)


def build_golden(out_path: Path = OUT_JSONL, keep_excluded: bool = False) -> list[dict]:
    if not SRC_XLS.exists():
        raise SystemExit(f"找不到人工标注文件：{SRC_XLS}")
    records, stat = read_golden_xls(SRC_XLS)

    print("行型统计：")
    for k, v in stat.items():
        print(f"  {k:16s} {v}")

    ok = True
    if stat.get("记录合计") != EXPECT_RECORDS:
        print(f"  ⚠️ 记录数 {stat.get('记录合计')} != 期望 {EXPECT_RECORDS}（见 DESIGN 2.1）")
        ok = False
    if stat.get("覆盖论文数") != EXPECT_PAPERS:
        print(f"  ⚠️ 论文数 {stat.get('覆盖论文数')} != 期望 {EXPECT_PAPERS}")
        ok = False

    if not keep_excluded:
        dropped = [r for r in records if r["paper_id"] in EXCLUDED_PAPERS]
        records = [r for r in records if r["paper_id"] not in EXCLUDED_PAPERS]
        if dropped:
            ids = ", ".join(str(p) for p in sorted(EXCLUDED_PAPERS))
            print(f"\n排除文献{ids}（有标注无 PDF，DESIGN 2.2 已定稿）：去掉 {len(dropped)} 条")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    filled = sum(1 for r in records for v in r["fields"].values() if v is not None)
    total = sum(len(r["fields"]) for r in records)
    n_papers = len({r["paper_id"] for r in records})
    print(f"\n写出 {out_path.relative_to(REPO_ROOT.parent)}：{len(records)} 条记录 / {n_papers} 篇（评测分母）")
    print(f"字段填充率 {filled}/{total} = {filled / total:.1%}（schema {schema_version()}）")
    print("原始表口径：" + ("与 DESIGN 2.1 一致 ✅" if ok else "与 DESIGN 不一致 ❌ 先查行型规则"))
    return records


def load_golden(path: Path = OUT_JSONL) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"缺少 {path}，先跑 python -m eval.golden")
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description="人工标注 .xls → golden.jsonl")
    ap.add_argument("--keep-excluded", action="store_true",
                    help="保留文献32/36/46（默认排除，见 DESIGN 2.2）")
    args = ap.parse_args()
    build_golden(keep_excluded=args.keep_excluded)


if __name__ == "__main__":
    main()
