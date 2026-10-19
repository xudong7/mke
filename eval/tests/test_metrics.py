"""eval/tests/test_metrics.py —— 评测尺子的单元测试（不依赖 pytest）。

覆盖：TP / FP / FN / TN、抽错要双计、容差边界、00 判缺失、枚举归一、实体归一、温度集合。
用法：python -m eval.tests.test_metrics   （失败退出码 1）
"""
from __future__ import annotations

import sys

from ..config import field_by_key
from ..metrics import judge, same
from .. import values


def _area():
    return field_by_key("比表面积(m²/g)")


def _unit():
    return field_by_key("组装方式")


def _surfactant():
    return field_by_key("表面活性剂")


def _temp():
    return field_by_key("合成温度")


CASES = [
    # (说明, 字段, gold, pred, 期望五态)
    ("数值相同", _area(), "720", "720 m²/g（S1）", "TP"),
    ("数值在 5% 容差边界内", _area(), "720", "756", "TP"),
    ("数值超出 5% 容差", _area(), "720", "760", "WRONG"),
    ("gold 缺失、预测有值 → 多抽", _area(), "—", "720", "FP"),
    ("gold 有值、预测缺失 → 漏抽", _area(), "720", "00", "FN"),
    ("两边都缺失 → TN", _area(), "00", "—", "TN"),
    ("数值解析不出 → 视为缺失(漏抽)", _area(), "720", "未直接给出 BET", "FN"),
    ("枚举：短标签 vs 整句", _unit(), "溶胶-凝胶", "溶胶-凝胶法（Co-condensation ...）", "TP"),
    ("枚举：碱性与酸性不同组", _unit(), "碱性软模板法", "酸性软模板法", "WRONG"),
    ("实体同义归一", _surfactant(), "Pluronic P123", "P123", "TP"),
    ("实体不同", _surfactant(), "CTAB", "Pluronic P123", "WRONG"),
    ("温度集合有交集且互相覆盖", _temp(), "80 °C老化4 h；450 °C焙烧", "450°C 焙烧; 80 °C 老化", "TP"),
    ("温度集合缺一个", _temp(), "80 °C；450 °C", "80 °C", "WRONG"),
]


def test_judge() -> list[str]:
    fails = []
    for desc, field, g, p, expect in CASES:
        got = judge(field, g, p)
        if got != expect:
            fails.append(f"{desc}: 期望 {expect} 实得 {got}（gold={g!r} pred={p!r}）")
    return fails


def test_missing_tokens() -> list[str]:
    fails = []
    for t in ("", "00", "—", "-", "null", "N/A", "  "):
        if not values.is_missing(t):
            fails.append(f"{t!r} 应判为缺失")
    for t in ("720", "溶胶-凝胶", "H2O"):
        if values.is_missing(t):
            fails.append(f"{t!r} 不应判为缺失")
    if not values.is_missing(None):
        fails.append("None 应判为缺失")
    return fails


def test_number_parsing() -> list[str]:
    fails = []
    cases = [
        ("281 m²/g（MCM-48/DPA-OTf [4]: 281 m2/g）", 281.0),
        (">1000", 1000.0),
        ("≈1000", 1000.0),
        ("ca. 3", 3.0),
        ("平均5.9", 5.9),
        ("未给出", None),
    ]
    for text, expect in cases:
        got = values.number_near_unit(text, r"m2/g|m²/g")
        if got != expect:
            fails.append(f"{text!r} 期望 {expect} 实得 {got}")
    return fails


def test_temperature() -> list[str]:
    got = values.temperature_set("室温搅拌12 h；60 °C真空干燥12 h")
    return [] if got == {60.0} else [f"温度抽取期望 {{60.0}} 实得 {got}"]


def test_wrong_counts_twice() -> list[str]:
    """抽错必须同时进 FP 与 FN（DESIGN 5.1）。"""
    from ..metrics import evaluate
    from .. import align as align_mod

    gold = [{"paper_id": 1, "record_index": 1, "fields": {"比表面积(m²/g)": "720"}, "note": None}]
    preds = [
        {
            "paper_number": 1,
            "records": [{"比表面积": "1400 m²/g"}],
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }
    ]
    aligned, missing = align_mod.align_all(gold, preds, mode="sequential")
    res = evaluate(aligned, missing, gold, "sequential")
    row = [r for r in res["fields"] if r["key"] == "比表面积(m²/g)"][0]
    fails = []
    if row["fp"] != 1 or row["fn"] != 1:
        fails.append(f"抽错应 FP=1 FN=1，实得 FP={row['fp']} FN={row['fn']}")
    if row["tp"] != 0:
        fails.append(f"抽错不应计 TP，实得 TP={row['tp']}")
    return fails


ALL_TESTS = [
    ("五态判定", test_judge),
    ("缺失值 token", test_missing_tokens),
    ("数值解析", test_number_parsing),
    ("温度集合", test_temperature),
    ("抽错双计 FP+FN", test_wrong_counts_twice),
]


def main() -> None:
    total_fails = 0
    for name, fn in ALL_TESTS:
        fails = fn()
        total_fails += len(fails)
        print(f"[{'PASS' if not fails else 'FAIL'}] {name}")
        for f in fails:
            print(f"       - {f}")
    print(f"\n{len(ALL_TESTS)} 组用例，{total_fails} 条失败")
    sys.exit(1 if total_fails else 0)


if __name__ == "__main__":
    main()
