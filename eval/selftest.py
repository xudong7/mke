"""eval/selftest.py —— 阳性对照：把 golden 自己当预测喂进评测。

期望：字段级 F1 = 100%、记录匹配率 = 100%。
只要不到 100%，就是评测代码的 bug，与模型无关（见《验证策略.md》第四节）。

用法：python -m eval.selftest   （失败时退出码 1）
"""
from __future__ import annotations

import sys

from . import align as align_mod
from .golden import load_golden
from .metrics import evaluate
from .synth import perfect_runs


def run() -> tuple[bool, dict]:
    gold = load_golden()
    preds = perfect_runs(gold)
    aligned, missing = align_mod.align_all(gold, preds, mode="value")
    result = evaluate(aligned, missing, gold, "value")
    ok = (
        abs(result["overall"]["f1"] - 1.0) < 1e-9
        and abs(result["records"]["match_rate"] - 1.0) < 1e-9
    )
    return ok, result


def main() -> None:
    ok, r = run()
    o, rec = r["overall"], r["records"]
    print("阳性对照（golden 自比）")
    print(f"  记录匹配率 {rec['aligned_records']}/{rec['gold_records']} = {rec['match_rate']:.4%}")
    print(f"  字段 P/R/F1 = {o['precision']:.4%} / {o['recall']:.4%} / {o['f1']:.4%}")
    bad = [row["key"] for row in r["fields"] if row["f1"] < 1.0]
    if bad:
        print(f"  未满分字段：{bad}")
    print("结论：" + ("PASS 尺子可信" if ok else "FAIL 评测代码有 bug，先修尺子"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
