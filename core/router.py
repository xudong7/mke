# core/router.py
import json

def route_paper(text: str, client, model_name: str):
    """
    使用轻量 LLM 调用，判断分析类型 + 推荐 skills。
    输出为中文说明，并附带简单推理。
    """
    system_prompt = """
你是一名材料化学文献筛选助手。请阅读给定的英文文献片段，
根据下面的定义判断该文献属于哪一类合成方式，并推荐应该使用的技能模块（skills）。

【分析类型（analysis_type）必须三选一】：
1）"soft_template_full(软模板)"：
   - 使用表面活性剂或嵌段共聚物（如 CTAB、P123、F127、PS-b-PEO 等）与硅源（例如 TEOS、TMOS、硅酸钠）协同组装形成介孔结构；
   - 这类文献需要进行完整、详细的参数抽取。

2）"core_shell_simple(预合成纳米颗粒参与形成复合结构)"：
   - 文献中先单独合成无机纳米颗粒（例如 Fe3O4、CdS 等），
   - 然后再将这些颗粒引入到介孔二氧化硅组装步骤中，形成 Fe3O4@nSiO2@mSiO2、CdS&mSiO2 等复合结构；
   - 这类文献只需要简单记录“组成”和“结构”，不做详细参数抽取。

3）"hard_template_simple(自模板/硬模板)"：
   - 文献明确提到 hard template、自模板（self-template）等，或者使用既有固体模板颗粒（如 p(GMA-co-EDMA)、RF 球等）作为模板；
   - 且未使用典型表面活性剂（CTAB、Pluronic、block copolymer 等）作为软模板；
   - 这类文献只需要记录“组装方式”（自模板/硬模板），不做详细参数抽取。

【可用 skill 名称（只能从这些名字中选择，不要编造新名字）】：
- screening_soft_template_zh
- assembly_mode_zh
- solution_and_concentrations_zh
- structure_and_properties_zh

你的任务：
1）阅读输入的英文文本（摘要 + 部分实验），判断 analysis_type；
2）根据类型选择需要使用的 skill 名称列表（selected_skills）；
   - 若是 soft_template_full，一般应包含上述四个 skill；
   - 若是 simple 类型，可以只保留 screening_soft_template_zh，或留空；
3）用【中文】简要说明你的判断依据和推理过程；
4）列出你用来判断的关键英文短语或句子，作为 source_snippets。

请严格输出一个 JSON 对象，格式为：
{
  "analysis_type": "soft_template_full | core_shell_simple | hard_template_simple",
  "selected_skills": ["skill_name1", "skill_name2", ...],
  "reason_zh": "用中文说明你如何判断，引用哪些关键信息",
  "source_snippets": [
    "用于判断的英文原句1",
    "英文原句2（如果有）"
  ]
}
"""

    user_prompt = f"""
下面是文献的部分内容（可能是摘要和部分合成过程，长度已截断）：

{text[:4000]}

请根据上述规则进行判断，并返回指定格式的 JSON。注意：解释和 reason_zh 一律用中文。
"""

    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0,
        response_format={"type": "json_object"}
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except Exception:
        # 如果解析失败，保守起见当作软模板全量分析
        return {
            "analysis_type": "soft_template_full",
            "selected_skills": [
                "screening_soft_template_zh",
                "assembly_mode_zh",
                "solution_and_concentrations_zh",
                "structure_and_properties_zh",
                "table_extraction_zh",
            ],
            "reason_zh": "模型输出解析失败，默认按照软模板法进行完整分析。",
            "source_snippets": []
        }
