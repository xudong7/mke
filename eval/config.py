"""eval/config.py —— 加载 eval/schema.yaml，供对齐与指标共用。

口径改动只改 schema.yaml，不要在这里写死字段名。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

SCHEMA_PATH = Path(__file__).with_name("schema.yaml")
DATA_DIR = Path(__file__).with_name("data")
REPO_ROOT = SCHEMA_PATH.parent.parent


@lru_cache(maxsize=1)
def schema() -> dict:
    with SCHEMA_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def schema_version() -> str:
    return str(schema()["meta"]["schema_version"])


def fields() -> list[dict]:
    """参与评测的 gold 字段（顺序即报表列顺序）。"""
    return schema()["fields"]


def field_by_key(key: str) -> dict:
    for f in fields():
        if f["key"] == key:
            return f
    raise KeyError(key)


def evaluated_fields() -> list[dict]:
    return [f for f in fields() if f.get("compare") != "not_evaluated"]


def tolerances() -> dict:
    return schema()["tolerances"]


MISSING_TOKENS = {str(t).strip().lower() for t in schema()["missing"]["gold_tokens"]} | {
    str(t).strip().lower() for t in schema()["missing"]["model_tokens"]
}
