"""eval/ablate.py —— 阴性对照：故意注入已知缺陷，看分数是否按预期下降。

如果注入了缺陷分数却不动，说明尺子没有区分度（见《验证策略.md》第四节）。
用法：python -m eval.ablate
"""
from __future__ import annotations

import copy
import re
import sys

from . import align as align_mod
from .golden import load_golden
from .metrics import evaluate
from .synth import perfect_runs


def _measure(gold, preds) -> dict:
    aligned, missing = align_mod.align_all(gold, preds, mode="value")
    return evaluate(aligned, missing, gold, "value")


def _f1(res: dict, key: str | None = None) -> float:
    if key:
        for row in res["fields"]:
            if row["key"] == key:
                return row["f1"]
    return res["overall"]["f1"]


def _clear_area(rec, _pid):
    rec["比表面积"] = "00"
    return rec


def _scale_numeric(rec, _pid):
    for k, unit in (("比表面积", "m2/g"), ("孔径", "nm")):
        m = re.search(r"(\d+(?:\.\d+)?)", str(rec.get(k) or ""))
        if m:
            rec[k] = f"{float(m.group(1)) * 2} {unit}"
    return rec


def main() -> None:
    gold = load_golden()
    base = _measure(gold, perfect_runs(gold))

    dup_preds = []
    for run in perfect_runs(gold):
        r = copy.deepcopy(run)
        r["records"] = r["records"] + copy.deepcopy(r["records"])
        dup_preds.append(r)

    half_preds = []
    for run in perfect_runs(gold):
        r = copy.deepcopy(run)
        r["records"] = r["records"][: max(1, len(r["records"]) // 2)]
        half_preds.append(r)

    cases = [
        ("完整（阳性对照）", base),
        ("比表面积整列清成 00", _measure(gold, perfect_runs(gold, _clear_area))),
        ("比表面积/孔径 数值 ×2", _measure(gold, perfect_runs(gold, _scale_numeric))),
        ("每条记录复制一遍", _measure(gold, dup_preds)),
        ("每篇丢掉一半记录", _measure(gold, half_preds)),
        ("只保留 1 篇预测", _measure(gold, perfect_runs(gold)[:1])),
    ]

    print(f"{'缺陷注入':24s} {'字段F1':>8s} {'比表面积F1':>10s} {'记录匹配率':>10s} {'多抽率':>8s}")
    print("-" * 68)
    for name, res in cases:
        print(
            f"{name:24s} {_f1(res):>8.1%} {_f1(res, '比表面积(m²/g)'):>10.1%} "
            f"{res['records']['match_rate']:>10.1%} {res['records']['unmatched_pred_rate']:>8.1%}"
        )

    checks = [
        ("阳性对照必须满分", _f1(cases[0][1]) > 0.999),
        ("清空字段 → 该字段 F1 归零", _f1(cases[1][1], "比表面积(m²/g)") == 0.0),
        (
            "数值 ×2 → 比表面积 F1 大幅下降（残余来自同篇内两样品本就相差 <5%，属容差固有性质）",
            _f1(cases[2][1], "比表面积(m²/g)") <= 0.10,
        ),
        (
            "复制记录 → 多抽数上升（字段 F1 不受影响，按设计）",
            cases[3][1]["records"]["unmatched_pred_rate"] > cases[0][1]["records"]["unmatched_pred_rate"],
        ),
        ("丢一半记录 → 记录匹配率下降", cases[4][1]["records"]["match_rate"] < cases[0][1]["records"]["match_rate"]),
        ("只留 1 篇 → 记录匹配率大幅下降", cases[5][1]["records"]["match_rate"] < 0.5),
    ]
    print()
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    print("\n结论：" + ("尺子有区分度" if ok else "尺子区分度不足，先修评测代码"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
