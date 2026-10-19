"""eval/align.py —— 记录级对齐（见 DESIGN 第 4 节）。

口径 A（主）：论文内按「值相似度」做贪心最大匹配，相似分 < 2 记为 unmatched。
口径 B（对照）：论文内按出现顺序一一对应，多出的算 extra、少了的算 miss。

gold 没有样品编号列，所以不能用主键对齐（DESIGN 4.1）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import values

MIN_SCORE = 2  # 见 DESIGN 4.2：低于此分判为 unmatched


@dataclass
class AlignedPaper:
    paper_id: int
    pairs: list[tuple[dict, dict]] = field(default_factory=list)   # (gold, pred)
    unmatched_gold: list[dict] = field(default_factory=list)
    unmatched_pred: list[dict] = field(default_factory=list)
    order_fallback: int = 0   # 值匹配分不开、按顺序兜底配上的对数

    @property
    def aligned(self) -> int:
        return len(self.pairs)


def _area(rec: dict) -> float | None:
    """rec 是 gold 记录时用 gold 字段名，是模型记录时用模型字段名。"""
    v = rec.get("比表面积(m²/g)", rec.get("比表面积"))
    return values.number_near_unit(v, r"m2/g|m²/g")


def _pore(rec: dict) -> float | None:
    v = rec.get("孔径分布(nm)", rec.get("孔径"))
    return values.number_near_unit(v, r"nm")


def _with_tol(g: float, p: float, rel: float | None, absv: float | None) -> bool:
    if absv is not None and abs(g - p) <= absv:
        return True
    if rel is not None and g != 0 and abs(g - p) / abs(g) <= rel:
        return True
    return False


def similarity(gold: dict, pred: dict, tol: dict) -> tuple[int, list[str]]:
    """返回 (分数, 命中的证据项)。分数越高越可能是同一条记录。"""
    score, hits = 0, []
    ga, pa = _area(gold), _area(pred)
    if ga is not None and pa is not None and _with_tol(ga, pa, *tol["面积"]):
        score += 2
        hits.append("比表面积")
    gp, pp = _pore(gold), _pore(pred)
    if gp is not None and pp is not None and _with_tol(gp, pp, *tol["孔径"]):
        score += 2
        hits.append("孔径")
    ge = values.entity_tokens("表面活性剂", gold.get("表面活性剂"))
    pe = values.entity_tokens("表面活性剂", pred.get("表面活性剂种类"))
    if ge and ge & pe:
        score += 1
        hits.append("表面活性剂")
    gt = values.temperature_set(gold.get("合成温度"))
    pt = values.temperature_set(pred.get("合成温度"))
    if gt and pt and any(any(abs(a - b) <= 5 for b in pt) for a in gt):
        score += 1
        hits.append("合成温度")
    return score, hits


def tolerance_table(metrics_tol: dict) -> dict:
    """把 metrics 里的容差转成对齐用的 (rel, abs) 二元组。"""
    return {
        "面积": (metrics_tol["specific_surface_area"]["rel"], metrics_tol["specific_surface_area"]["abs"]),
        "孔径": (metrics_tol["pore_size"]["rel"], metrics_tol["pore_size"]["abs"]),
    }


def align_paper(paper_id: int, gold_records: list[dict], pred_records: list[dict], tol: dict) -> AlignedPaper:
    out = AlignedPaper(paper_id=paper_id)
    scored = []
    for gi, g in enumerate(gold_records):
        for pi, p in enumerate(pred_records):
            s, hits = similarity(g["fields"], p, tol)
            if s > 0:
                scored.append((s, gi, pi, hits))
    scored.sort(key=lambda x: (-x[0], x[1], x[2]))

    used_g, used_p = set(), set()
    for s, gi, pi, _hits in scored:
        if s < MIN_SCORE or gi in used_g or pi in used_p:
            continue
        used_g.add(gi)
        used_p.add(pi)
        out.pairs.append((gold_records[gi], pred_records[pi]))

    # 兜底：剩下的按出现顺序配对。
    # 值匹配的作用是「处理顺序不一致」，不是「值分不开就判未匹配」——金标准与预测数量一致时，
    # 分不开的记录本来就该按顺序对上；数量对不上的部分才是真正的 unmatched。
    rest_g = [i for i in range(len(gold_records)) if i not in used_g]
    rest_p = [i for i in range(len(pred_records)) if i not in used_p]
    for gi, pi in zip(rest_g, rest_p):
        out.order_fallback += 1
        out.pairs.append((gold_records[gi], pred_records[pi]))
    used_g.update(rest_g[: len(rest_p)])
    used_p.update(rest_p[: len(rest_g)])

    out.unmatched_gold = [g for i, g in enumerate(gold_records) if i not in used_g]
    out.unmatched_pred = [p for i, p in enumerate(pred_records) if i not in used_p]
    return out


def align_sequential(paper_id: int, gold_records: list[dict], pred_records: list[dict]) -> AlignedPaper:
    """口径 B：顺序一一对应。"""
    out = AlignedPaper(paper_id=paper_id)
    for i in range(min(len(gold_records), len(pred_records))):
        out.pairs.append((gold_records[i], pred_records[i]))
    out.unmatched_gold = gold_records[len(pred_records):] if len(gold_records) > len(pred_records) else []
    out.unmatched_pred = pred_records[len(gold_records):] if len(pred_records) > len(gold_records) else []
    return out


def align_all(gold: list[dict], preds: list[dict], mode: str = "value") -> tuple[list[AlignedPaper], list[dict]]:
    """返回 (对齐结果, 没有对应预测的 gold 论文清单)。"""
    from .metrics import TOLERANCES

    tol = tolerance_table(TOLERANCES)
    gold_by_paper: dict[int, list[dict]] = {}
    for g in gold:
        gold_by_paper.setdefault(g["paper_id"], []).append(g)
    pred_by_paper: dict[int, list[dict]] = {}
    for p in preds:
        n = p.get("paper_number")
        if n is not None and p.get("records"):
            pred_by_paper.setdefault(n, []).append(p)

    results, missing_papers = [], []
    for pid in sorted(gold_by_paper):
        g = sorted(gold_by_paper[pid], key=lambda x: x["record_index"])
        run = pred_by_paper.get(pid)
        if not run:
            missing_papers.append({"paper_id": pid, "gold_records": len(g)})
            results.append(AlignedPaper(paper_id=pid, unmatched_gold=g))
            continue
        pred_records = max(run, key=lambda r: str(r.get("updated_at") or r.get("created_at") or ""))["records"]
        if mode == "sequential":
            results.append(align_sequential(pid, g, pred_records))
        else:
            results.append(align_paper(pid, g, pred_records, tol))
    return results, missing_papers
