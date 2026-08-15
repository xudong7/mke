# backend/deps.py
"""共享依赖：路径常量、惰性 OpenAI 客户端、SkillManager 单例。

注意：不要 import config.py —— 它在导入时就会因缺少 OPENAI_API_KEY 抛错，
会阻断论文浏览等不需要 LLM 的功能。这里直接读环境变量（默认值与 config.py 一致）。
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from core.skills_manager import SkillManager

load_dotenv()  # 幂等，加载 .env（若存在）

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CORPUS_DIR = DATA_DIR / "new_papers_info-100"
UPLOADS_DIR = DATA_DIR / "uploads"
ANNOTATIONS_DIR = DATA_DIR / "annotations"
SKILLS_DIR = PROJECT_ROOT / "skills"

_client: OpenAI | None = None
_skill_manager: SkillManager | None = None


def get_client() -> OpenAI:
    """惰性创建 OpenAI 客户端；未配置 key 时抛 RuntimeError（由调用方转 503）。"""
    global _client
    if _client is None:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("未配置 OPENAI_API_KEY，请在 .env 或环境变量中设置")
        _client = OpenAI(
            api_key=key,
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com"),
        )
    return _client


def get_model_name() -> str:
    return os.environ.get("MODEL_NAME", "deepseek-chat")


def get_skill_manager() -> SkillManager:
    global _skill_manager
    if _skill_manager is None:
        _skill_manager = SkillManager(SKILLS_DIR)
    return _skill_manager
