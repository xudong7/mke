"""eval/metrics.py —— 字段级 / 记录级指标（口径见 DESIGN 第 5 节）。

判定五态：TP / FP(多抽) / FN(漏抽) / TN(两边都缺) / WRONG(抽错，计 FP+FN)。
TN 不进入 P/R/F1 分母，只单列「一致缺失率」。
"""
from __future__ import annotations

import re
from collections import defaultdict

from . import values
from .config import evaluated_fields, schema, schema_version

MAX_SAMPLES = 5


def _parse_tol(text: str) -> dict:
    rel = absv = None
    for num, pct in re.findall(r"(\d+(?:\.\d+)?)\s*(%?)", str(text)):
        if pct == "%" and rel is None:
            rel = float(num) / 100
        elif pct == "" and absv is None:
            absv = float(num)
    return {"rel": rel, "abs": absv}


TOLERANCES = {k: _parse_tol(v) for k, v in schema()["tolerances"].items()}

FIELD_TOL = {
    "比表面积(m²/g)": "specific_surface_area",
    "孔径分布(nm)": "pore_size",
    "合成温度": "temperature",
    "表面活性剂浓度": "concentration",
}

FIELD_UNIT = {
    "比表面积(m²/g)": r"m2/g|m²/g",
    "孔径分布(nm)": r"nm",
}


# ---------------------------------------------------------------- 单字段比较

def _numeric(field_key: str, v) -> float | None:
    pat = FIELD_UNIT.get(field_key)
    return values.number_near_unit(v, pat) if pat else values.first_number(v)


def _within(g: float, p: float, tol: dict) -> bool:
    if tol.get("abs") is not None and abs(g - p) <= tol["abs"]:
        return True
    if tol.get("rel") is not None and g != 0 and abs(g - p) / abs(g) <= tol["rel"]:
        return True
    return False


def _set_prf1(g: set, p: set) -> float:
    if not g and not p:
        return 1.0
    if not g or not p:
        return 0.0
    tp = len(g & p)
    if tp == 0:
        return 0.0
    prec, rec = tp / len(p), tp / len(g)
    return 2 * prec * rec / (prec + rec)


def value_present(field: dict, v) -> bool:
    """该字段是否「有可比内容」。

    数值字段解析不出数字算缺失；解析出来是 0 也算缺失（0 m²/g、0 nm 在本领域不是合法观测值，
    实测 gold 里有 7 条 比表面积 直接写 0，属占位写法，见 schema.yaml 的 zero_vs_missing）。
    """
    if values.is_missing(v):
        return False
    if field["compare"] == "numeric":
        n = _numeric(field["key"], v)
        return n is not None and n != 0
    if field["compare"] == "numeric_set":
        ts = values.temperature_set(v)
        return bool(ts) and ts != {0.0}
    if field["compare"] == "token_set":
        # 与数值字段同理：解析不出任何实体/数值 token 就当作缺失，不进分母
        return bool(values.token_set(field["key"], v))
    if field["compare"] == "loose_text":
        return bool(values.keywords(v))
    return True


def same(field: dict, g, p) -> tuple[bool, str]:
    """归一后是否算「抽对」。返回 (是否相同, 说明)。"""
    key, mode = field["key"], field["compare"]
    if mode == "enum_group":
        gg, pg = values.enum_group(key, g), values.enum_group(key, p)
        return gg == pg, f"{gg} vs {pg}"
    if mode == "entity":
        gs, ps = values.entity_tokens(key, g), values.entity_tokens(key, p)
        return gs == ps, f"{sorted(gs)} vs {sorted(ps)}"
    if mode == "numeric":
        tol = TOLERANCES.get(FIELD_TOL.get(key, "concentration"), {"rel": 0.05, "abs": 0.0})
        gn, pn = _numeric(key, g), _numeric(key, p)
        if gn is None or pn is None:
            return False, f"数值不可解析：{g!r} vs {p!r}"
        return _within(gn, pn, tol), f"{gn} vs {pn}"
    if mode == "numeric_set":
        gt, pt = values.temperature_set(g), values.temperature_set(p)
        # 与 token_set 一致：gold 的温度全部出现即算命中，预测多出的温度记入说明不扣分
        missing = [a for a in gt if not any(abs(a - b) <= 5 for b in pt)]
        extra = [b for b in pt if not any(abs(b - a) <= 5 for a in gt)]
        return (bool(gt) and not missing), f"漏温度={sorted(missing)} 多温度={sorted(extra)}"
    if mode == "token_set":
        gs, ps = values.token_set(key, g), values.token_set(key, p)
        # 召回导向：gold 的 token 全部出现在预测里即算命中。
        # 模型写得更详细（多出体积/质量等）不算错，只记进样例说明。
        missing = gs - ps
        ok = bool(gs) and not missing
        detail = f"漏 token={sorted(missing)}；集合 F1={_set_prf1(gs, ps):.2f}"
        return ok, detail
    if mode == "loose_text":
        gk, pk = values.keywords(g), values.keywords(p)
        cov = len(gk & pk) / len(gk) if gk else 0.0
        return cov >= 0.5, f"gold 关键词覆盖率 {cov:.2f}"
    return values.norm_text(g) == values.norm_text(p), ""


def judge(field: dict, g, p) -> str:
    """五态判定。"""
    gp, pp = value_present(field, g), value_present(field, p)
    if not gp and not pp:
        return "TN"
    if not gp:
        return "FP"
    if not pp:
        return "FN"
    return "TP" if same(field, g, p)[0] else "WRONG"


# ---------------------------------------------------------------- 总体指标

def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return prec, rec, f1


def evaluate(aligned_papers: list, missing_papers: list[dict], gold: list[dict], mode: str) -> dict:
    fields_eval = evaluated_fields()
    stat: dict[str, dict] = {f["key"]: defaultdict(int, key=f["key"], compare=f["compare"]) for f in fields_eval}
    samples: dict[str, list] = {"漏抽": [], "多抽": [], "抽错": []}

    aligned_total = 0
    for ap in aligned_papers:
        aligned_total += ap.aligned
        for g, p in ap.pairs:
            for f in fields_eval:
                key, mk = f["key"], f.get("model_key")
                gv = g["fields"].get(key)
                pv = p.get(mk) if mk else None
                st = judge(f, gv, pv)
                stat[key][st] += 1
                if st in ("FN", "FP", "WRONG") and len(samples[_bucket(st)]) < MAX_SAMPLES:
                    samples[_bucket(st)].append(
                        {
                            "paper_id": g["paper_id"],
                            "record_index": g["record_index"],
                            "field": key,
                            "gold": gv,
                            "pred": pv,
                            "note": same(f, gv, pv)[1] if st == "WRONG" else "",
                        }
                    )

    rows = []
    for f in fields_eval:
        s = stat[f["key"]]
        # 抽错（WRONG）同时计 FP 与 FN（DESIGN 5.1）
        tp = s["TP"]
        wrong = s["WRONG"]
        fp_total = s["FP"] + s["WRONG"]
        fn_total = s["FN"] + s["WRONG"]
        prec, rec, f1 = _prf(tp, fp_total, fn_total)
        denom = aligned_total or 1
        gold_present = tp + wrong + s["FN"]          # 该字段在 gold 侧有值的记录数
        rows.append(
            {
                "key": f["key"],
                "compare": f["compare"],
                "tp": tp,
                "fp": fp_total,
                "fn": fn_total,
                "tn": s["TN"],
                "precision": prec,
                "recall": rec,
                "f1": f1,
                "accuracy": tp / gold_present if gold_present else 0.0,
                "coverage": gold_present / denom,
                "both_missing": s["TN"] / denom if denom else 0.0,
            }
        )

    tp = sum(r["tp"] for r in rows)
    fp = sum(r["fp"] for r in rows)
    fn = sum(r["fn"] for r in rows)
    prec, rec, f1 = _prf(tp, fp, fn)

    gold_total = len(gold)
    return {
        "meta": {
            "schema_version": schema_version(),
            "mode": mode,
            "gold_records": gold_total,
            "aligned_records": aligned_total,
            "unmatched_gold": sum(len(a.unmatched_gold) for a in aligned_papers),
            "unmatched_pred": sum(len(a.unmatched_pred) for a in aligned_papers),
            "papers_total": len(aligned_papers),
            "papers_without_pred": len(missing_papers),
        },
        "fields": rows,
        "overall": {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": prec, "recall": rec, "f1": f1,
            "accuracy": tp / (aligned_total * len(rows)) if aligned_total and rows else 0.0,
        },
        "records": {
            "gold_records": gold_total,
            "aligned_records": aligned_total,
            "match_rate": aligned_total / gold_total if gold_total else 0.0,
            "unmatched_gold": sum(len(a.unmatched_gold) for a in aligned_papers),
            "unmatched_pred": sum(len(a.unmatched_pred) for a in aligned_papers),
            "unmatched_pred_rate": (
                sum(len(a.unmatched_pred) for a in aligned_papers) / gold_total if gold_total else 0.0
            ),
            "order_fallback_pairs": sum(a.order_fallback for a in aligned_papers),
            "table_row_recall": None,  # 需要 parse_report.json（解析线产出），第一周还不可用
        },
        "missing_papers": missing_papers,
        "samples": samples,
    }


def _bucket(status: str) -> str:
    return {"FN": "漏抽", "FP": "多抽", "WRONG": "抽错"}[status]
