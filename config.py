# config.py
import os
from pathlib import Path

from dotenv import load_dotenv

# 加载 .env 文件中的环境变量(若存在)
load_dotenv()

# 路径配置
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_MD_DIR = DATA_DIR / "new_papers_info-100"
OUTPUT_DIR = DATA_DIR / "outputs"
SKILLS_DIR = PROJECT_ROOT / "skills"

# 模型和 API 配置(从环境变量读取,勿硬编码密钥;参考 .env.example)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com")
MODEL_NAME = os.environ.get("MODEL_NAME", "deepseek-chat")

if not OPENAI_API_KEY:
    raise RuntimeError(
        "未找到 OPENAI_API_KEY 环境变量。\n"
        "请复制 .env.example 为 .env 并填入真实密钥,"
        "或在运行前执行 export OPENAI_API_KEY=sk-xxx。"
    )

# 输出文件名
DEFAULT_OUTPUT_EXCEL = OUTPUT_DIR / "介孔材料批量抽取结果.xlsx"

USE_LLM_FORMATTER = False
USE_STRUCTURIZER = True
