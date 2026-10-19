"""eval/synth.py —— 用 golden 造「完美预测」，供阳性 / 阴性对照使用。

gold 字段 → 模型字段的映射取自 schema.yaml 的 model_key。
"""
from __future__ import annotations

from .config import fields

_MAP = [(f["key"], f.get("model_key")) for f in fields() if f.get("model_key")]


def to_model_record(gold_fields: dict) -> dict:
    out = {}
    for gk, mk in _MAP:
        out[mk] = gold_fields.get(gk)
    return out


def perfect_runs(gold: list[dict], mutate=None) -> list[dict]:
    """按论文聚合成「预测 run」；mutate(record, paper_id) 可在造好后改坏数据。"""
    by_paper: dict[int, list[dict]] = {}
    for rec in gold:
        by_paper.setdefault(rec["paper_id"], []).append(rec)

    runs = []
    for pid, recs in sorted(by_paper.items()):
        records = []
        for rec in sorted(recs, key=lambda r: r["record_index"]):
            model_rec = to_model_record(rec["fields"])
            if mutate:
                model_rec = mutate(model_rec, pid) or model_rec
            records.append(model_rec)
        runs.append(
            {
                "run_id": f"synth-{pid}",
                "paper_id": f"文献{pid}",
                "paper_number": pid,
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "status": "done",
                "model": "synth",
                "prompt_version": "synth",
                "record_count": len(records),
                "records": records,
            }
        )
    return runs
