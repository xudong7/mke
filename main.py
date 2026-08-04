# main.py
import pandas as pd
import json
from datetime import datetime

from config import (
    RAW_MD_DIR,
    OUTPUT_DIR,
    SKILLS_DIR,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    MODEL_NAME,
    DEFAULT_OUTPUT_EXCEL,
    USE_LLM_FORMATTER,
    USE_STRUCTURIZER,
)
from core.skills_manager import SkillManager
from core.extractor import MesoporousExtractor
from core.postprocess import simple_format_results
from core.formatter_agent import normalize_results_with_llm
from core.structurizer_agent import structurize_results
  # 如果暂时不用，可以先注释掉

RAW_JSON_PATH = OUTPUT_DIR / f"raw_results_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
RAW_JSON_PRETTY = OUTPUT_DIR / f"raw_results_pretty_{datetime.now():%Y%m%d_%H%M%S}.json"
NORM_JSON_PATH = OUTPUT_DIR / f"normalized_results_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
NORM_JSON_PRETTY = OUTPUT_DIR / f"normalized_results_pretty_{datetime.now():%Y%m%d_%H%M%S}.json"

def main():
    # 确保输出目录存在
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 初始化 skill 管理器
    skill_manager = SkillManager(SKILLS_DIR)

    # 初始化抽取器
    extractor = MesoporousExtractor(
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL,
        model_name=MODEL_NAME,
        skill_manager=skill_manager,
    )

    # 批量处理 md
    all_results = extractor.batch_process_md_dir(RAW_MD_DIR)

    if not all_results:
        print("\n... 没有任何数据被提取出来。")
        return

    #  保存原始 JSON 结果（方便调试）
    with RAW_JSON_PATH.open("w", encoding="utf-8") as f:
        for r in all_results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    
    with RAW_JSON_PRETTY.open("w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    #  简单规则格式化
    formatted = simple_format_results(all_results)

    if USE_LLM_FORMATTER:
        formatted = normalize_results_with_llm(formatted, extractor.client, extractor.model_name)
    if USE_STRUCTURIZER:
        formatted = structurize_results(formatted, extractor.client, extractor.model_name)

    #  保存规范化 JSON
    with NORM_JSON_PATH.open("w", encoding="utf-8") as f:
        for r in formatted:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    
    with NORM_JSON_PRETTY.open("w", encoding="utf-8") as f:
        json.dump(formatted, f, ensure_ascii=False, indent=2)

    
    # 保存为 Excel
    df = pd.DataFrame(formatted)
    df.to_excel(DEFAULT_OUTPUT_EXCEL, index=False)

    print(f"\n🎉 所有处理完成！共 {len(formatted)} 条数据。")
    print(f"📊 结果已保存至: {DEFAULT_OUTPUT_EXCEL.resolve()}")


if __name__ == "__main__":
    main()
