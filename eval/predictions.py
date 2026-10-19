"""eval/predictions.py —— data/runs/*.json → eval/data/predictions.jsonl

一条 run 输出一行；同一篇论文可能有多条 run，评测时用 --latest 只取最新（见 DESIGN 5「同一评测集」）。

用法：python -m eval.predictions [--latest]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .config import DATA_DIR, REPO_ROOT

RUNS_DIR = REPO_ROOT / "data" / "runs"
OUT_JSONL = DATA_DIR / "predictions.jsonl"


def paper_number(paper_id: str) -> int | None:
    """'介孔文献10_output' / '介孔文献10' / '介孔材料8' / 'paper_10' → 10"""
    m = re.search(r"(\d+)", str(paper_id))
    return int(m.group(1)) if m else None


def iter_runs(runs_dir: Path = RUNS_DIR) -> list[dict]:
    out = []
    for f in sorted(runs_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  ⚠️ 跳过损坏的 run：{f.name}")
            continue
        records = data.get("records") or []
        out.append(
            {
                "run_id": data.get("id") or f.stem,
                "paper_id": data.get("paper_id"),
                "paper_number": paper_number(data.get("paper_id")),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "status": data.get("status"),
                "model": data.get("model"),  # 现阶段的 run 还没记录，留空
                "prompt_version": data.get("prompt_version"),
                "record_count": len(records),
                "records": records,
            }
        )
    return out


def latest_per_paper(runs: list[dict]) -> list[dict]:
    """同一篇论文多次 run 时，只保留 updated_at/created_at 最新的一条。"""
    best: dict[int, dict] = {}
    for r in runs:
        n = r.get("paper_number")
        if n is None or not r.get("records"):
            continue
        key = str(r.get("updated_at") or r.get("created_at") or "")
        if n not in best or key > str(best[n].get("updated_at") or best[n].get("created_at") or ""):
            best[n] = r
    return [best[k] for k in sorted(best)]


def build(out_path: Path = OUT_JSONL, latest: bool = False) -> list[dict]:
    runs = iter_runs()
    kept = latest_per_paper(runs) if latest else runs
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    by_paper: dict[int, int] = {}
    for r in kept:
        n = r.get("paper_number")
        if n is not None:
            by_paper[n] = by_paper.get(n, 0) + 1
    print(f"扫描 {len(runs)} 条 run，写出 {len(kept)} 条到 {out_path.relative_to(REPO_ROOT.parent)}"
          + ("（每篇只留最新）" if latest else ""))
    print(f"覆盖论文 {len(by_paper)} 篇；记录合计 {sum(r['record_count'] for r in kept)} 条")
    multi = {k: v for k, v in by_paper.items() if v > 1}
    if multi:
        print(f"  注意：这些论文有多条 run（未加 --latest 会重复计入）→ {multi}")
    return kept


def load_predictions(path: Path = OUT_JSONL) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"缺少 {path}，先跑 python -m eval.predictions")
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description="导出模型预测（来自 data/runs）")
    ap.add_argument("--latest", action="store_true", help="同一篇论文只保留最新一次 run")
    args = ap.parse_args()
    build(latest=args.latest)


if __name__ == "__main__":
    main()
