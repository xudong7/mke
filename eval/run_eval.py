"""eval/run_eval.py —— 评测入口：一条命令出 eval/report.md。

用法：
    python -m eval.run_eval                     # 用 eval/data 下的默认文件
    python -m eval.run_eval --tag baseline      # 在报表标题里打标签

报表口径见 eval/DESIGN.md 第 6 节。
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from . import align as align_mod
from . import parsed as parsed_mod
from .config import DATA_DIR, REPO_ROOT, schema_version
from .golden import load_golden
from .metrics import _prf, evaluate, evaluated_fields, judge
from .predictions import load_predictions

REPORT_PATH = Path(__file__).with_name("report.md")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _dedupe_latest(preds: list[dict]) -> list[dict]:
    best: dict[int, dict] = {}
    for r in preds:
        n = r.get("paper_number")
        if n is None:
            continue
        key = str(r.get("updated_at") or r.get("created_at") or "")
        if n not in best or key > str(best[n].get("updated_at") or best[n].get("created_at") or ""):
            best[n] = r
    return [best[k] for k in sorted(best)]


def _per_paper(aligned_papers: list) -> list[dict]:
    fe = evaluated_fields()
    rows = []
    for ap in aligned_papers:
        tp = fp = fn = 0
        for g, p in ap.pairs:
            for f in fe:
                gv = g["fields"].get(f["key"])
                pv = p.get(f.get("model_key")) if f.get("model_key") else None
                st = judge(f, gv, pv)
                if st == "TP":
                    tp += 1
                elif st == "WRONG":
                    # 抽错：FP 与 FN 各记一次（DESIGN 5.1）
                    fp += 1
                    fn += 1
                elif st == "FP":
                    fp += 1
                elif st == "FN":
                    fn += 1
        _p, _r, f1 = _prf(tp, fp, fn)
        rows.append(
            {
                "paper_id": ap.paper_id,
                "gold": ap.aligned + len(ap.unmatched_gold),
                "aligned": ap.aligned,
                "unmatched": len(ap.unmatched_gold),
                "tp": tp, "fp": fp, "fn": fn, "f1": f1,
            }
        )
    return rows


def _fmt(x: float) -> str:
    return f"{x*100:.1f}%"


def build_report(tag: str = "", pred_path: Path | None = None, gold_path: Path | None = None) -> str:
    gold_path = gold_path or (DATA_DIR / "golden.jsonl")
    pred_path = pred_path or (DATA_DIR / "predictions.jsonl")

    gold = load_golden(gold_path)
    preds_all = load_predictions(pred_path)
    preds = _dedupe_latest(preds_all)

    # 解析线产物（可选）：有就能启用 parser_version 与「含表/无表」分层
    parsed_summary = parsed_mod.summary()
    parser_versions = {
        (parsed_mod.load(n).report or {}).get("parser_version")
        for n in sorted(parsed_mod.available_papers())
        if parsed_mod.load(n) and parsed_mod.load(n).report
    }
    parser_versions.discard(None)
    parser_desc = ", ".join(sorted(str(v) for v in parser_versions)) if parser_versions else "未知（解析线尚未交付 data/parsed）"

    out = []
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    out.append(f"# 评测报表{(' · ' + tag) if tag else ''}")
    out.append("")
    out.append("```")
    out.append(f"schema_version  {schema_version()}")
    out.append(f"prompt_version  {preds[0].get('prompt_version') if preds else '未知（run 未记录，见任务九）'}")
    out.append(f"model           {preds[0].get('model') if preds else '未知（run 未记录，见任务九）'}")
    out.append(f"parser_version  {parser_desc}")
    out.append(
        f"解析产物        {parsed_summary['available']} 篇可用"
        + (f"，含表 {parsed_summary['with_tables']} 篇 / 表 {parsed_summary['tables_total']} 张"
           if parsed_summary["available"] else "（未交付）")
    )
    out.append(f"golden.jsonl    {gold_path.name} sha256={_sha256(gold_path)}  {len(gold)} 条记录")
    out.append(f"predictions     {pred_path.name} sha256={_sha256(pred_path)}  {len(preds)} 篇（已按论文去重取最新）")
    out.append(f"评测论文        共 {len(gold) and len({g['paper_id'] for g in gold})} 篇，其中有预测 {len(preds)} 篇")
    out.append(f"运行命令        python -m eval.run_eval{' --tag ' + tag if tag else ''}")
    out.append(f"运行时间        {stamp}   temperature=0")
    out.append("```")
    out.append("")

    # 口径 A 与口径 B 都跑（DESIGN 4.2）
    results = {}
    for mode in ("value", "sequential"):
        aligned, missing = align_mod.align_all(gold, preds, mode=mode)
        results[mode] = (aligned, missing, evaluate(aligned, missing, gold, mode))

    a_aligned, a_missing, a = results["value"]
    b_aligned, _b_missing, b = results["sequential"]

    out.append("## 1. 总览")
    out.append("")
    out.append("| 口径 | 对齐记录 | 未匹配 gold | 未匹配预测 | 字段 P | 字段 R | 字段 F1 |")
    out.append("| --- | --- | --- | --- | --- | --- | --- |")
    for name, key in (("A 值对齐（主）", "value"), ("B 顺序对齐（对照）", "sequential")):
        r = results[key][2]
        out.append(
            f"| {name} | {r['meta']['aligned_records']} | {r['meta']['unmatched_gold']} | "
            f"{r['meta']['unmatched_pred']} | {_fmt(r['overall']['precision'])} | "
            f"{_fmt(r['overall']['recall'])} | **{_fmt(r['overall']['f1'])}** |"
        )
    out.append("")
    out.append(f"记录匹配率（口径 A）= {a['records']['aligned_records']} / {a['records']['gold_records']} "
               f"= {_fmt(a['records']['match_rate'])}；表格行召回：{a['records']['table_row_recall'] or '暂不可用（需要解析线的 parse_report.json）'}")
    if a_missing:
        ids = [int(m["paper_id"]) for m in a_missing]
        head = ", ".join(str(i) for i in ids[:15])
        out.append("")
        tail = "…" if len(ids) > 15 else ""
        out.append(f"> 有 gold 但没有预测的论文 {len(a_missing)} 篇（第一周只有 3 篇有 run）：{head}{tail}")
    out.append("")

    out.append("## 2. 字段级（口径 A）")
    out.append("")
    out.append("覆盖率 = 该字段在 gold 侧有值的记录占比；一致缺失 = 两边都判缺失的占比（不进 P/R/F1 分母）。")
    out.append("")
    out.append("| 字段 | 比法 | P | R | F1 | accuracy | 覆盖率 | 一致缺失 | TP | FP | FN |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in a["fields"]:
        out.append(
            f"| {r['key']} | {r['compare']} | {_fmt(r['precision'])} | {_fmt(r['recall'])} | "
            f"{_fmt(r['f1'])} | {_fmt(r['accuracy'])} | {_fmt(r['coverage'])} | "
            f"{_fmt(r['both_missing'])} | {r['tp']} | {r['fp']} | {r['fn']} |"
        )
    o = a["overall"]
    out.append(
        f"| **合计（micro）** | | {_fmt(o['precision'])} | {_fmt(o['recall'])} | "
        f"**{_fmt(o['f1'])}** | {_fmt(o['accuracy'])} | | | {o['tp']} | {o['fp']} | {o['fn']} |"
    )
    out.append("")

    out.append("## 3. 逐篇（口径 A）")
    out.append("")
    out.append("| 论文 | gold 记录 | 对齐 | 未匹配 | 字段 F1 |")
    out.append("| --- | --- | --- | --- | --- |")
    rows = _per_paper(a_aligned)
    shown = [r for r in rows if r["aligned"]]
    for row in shown:
        out.append(
            f"| 文献{row['paper_id']} | {row['gold']} | {row['aligned']} | {row['unmatched']} | {_fmt(row['f1'])} |"
        )
    hidden = len(rows) - len(shown)
    if hidden:
        out.append(f"| （其余 {hidden} 篇无预测，未列出） | | | | |")
    out.append("")

    out.append("## 4. 分层（口径 A）")
    out.append("")
    gold_per_paper = {p: sum(1 for g in gold if g["paper_id"] == p) for p in {g["paper_id"] for g in gold}}
    single = {p for p, n in gold_per_paper.items() if n == 1}
    multi = set(gold_per_paper) - single
    out.append("| 分层 | 论文数 | 对齐记录 | 字段 F1 |")
    out.append("| --- | --- | --- | --- |")
    for name, ids in (("单记录论文", single), ("多记录论文", multi)):
        sub = [ap for ap in a_aligned if ap.paper_id in ids]
        rows = _per_paper(sub)
        tp = sum(r["tp"] for r in rows)
        fp = sum(r["fp"] for r in rows)
        fn = sum(r["fn"] for r in rows)
        _, _, f1 = _prf(tp, fp, fn)
        out.append(f"| {name} | {len(ids)} | {sum(r['aligned'] for r in rows)} | {_fmt(f1)} |")
    has_tables = {
        n for n in parsed_mod.available_papers()
        if (parsed_mod.load(n) and parsed_mod.load(n).table_count)
    }
    if has_tables:
        without = set(parsed_mod.available_papers()) - has_tables
        for name, ids in (("含表论文", has_tables), ("无表论文", without)):
            sub = [ap for ap in a_aligned if ap.paper_id in ids]
            rows = _per_paper(sub)
            tp = sum(r["tp"] for r in rows)
            fp = sum(r["fp"] for r in rows)
            fn = sum(r["fn"] for r in rows)
            _, _, f1 = _prf(tp, fp, fn)
            out.append(f"| {name} | {len(ids)} | {sum(r['aligned'] for r in rows)} | {_fmt(f1)} |")
    else:
        out.append("| 含表 / 无表 | 待解析线交付 parse_report.json 后启用 | | |")
    out.append("| 文献类型（软模板/复合/硬模板） | 需人工给 20 篇子集打标（DESIGN 5.4） | | |")
    out.append("")

    out.append("## 5. 混淆样例（口径 A，各取前 5 条）")
    out.append("")
    for bucket in ("漏抽", "多抽", "抽错"):
        items = a["samples"].get(bucket, [])
        out.append(f"**{bucket}**（{len(items)} 条样例）")
        out.append("")
        if not items:
            out.append("（无）")
        else:
            for s in items:
                out.append(
                    f"- 文献{s['paper_id']} 记录#{s['record_index']} `{s['field']}`："
                    f"gold=`{str(s['gold'])[:70]}` → pred=`{str(s['pred'])[:70]}`"
                    + (f"（{s['note']}）" if s.get("note") else "")
                )
        out.append("")

    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="跑评测并生成 eval/report.md")
    ap.add_argument("--tag", default="", help="报表标签，如 baseline")
    ap.add_argument("--gold", type=Path, default=None)
    ap.add_argument("--pred", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=REPORT_PATH)
    args = ap.parse_args()

    text = build_report(args.tag, args.pred, args.gold)
    args.out.write_text(text, encoding="utf-8")
    print(f"写出 {args.out.relative_to(REPO_ROOT.parent)}\n")

    # 控制台只打总览，细节看报表
    for line in text.splitlines():
        if line.startswith("| ") and ("F1" in line or "合计" in line or "口径" in line):
            print(line)


if __name__ == "__main__":
    main()
