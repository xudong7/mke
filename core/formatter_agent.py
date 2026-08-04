# core/formatter_agent.py
import json

def normalize_results_with_llm(results_list, client, model_name: str):
    """
    使用 LLM 对一批结果进行格式规范化。
    即使 LLM 返回的 JSON 不合法，也不要让整个程序崩溃：打印警告，返回原 results_list。
    """
    if not results_list:
        return results_list

    system_prompt = """
你是一名“结果格式规范助手”。输入是一组已经抽取好的实验记录（results 数组）。
任务：
1）统一字段名和结构，缺失字段填 "00"；
2）统一单位和表达方式（温度 XX °C，时间 XX h，浓度 mg/mL 或 mL/mL 等）；
3）保持每个字段后面原有的英文原文短语（括号中的英文），不要杜撰；
4）发现明显不合理的数值（如 pH > 14，负的比表面积等）时，将该字段值改为 "00"，并在“其他变量”中简要说明。

非常重要：
- 你只能返回一个【单一的 JSON 对象】，结构必须是：
  {
    "results": [ {...}, {...}, ... ]
  }
- 对每条记录已有的字段都应尽量保留，尤其是“来源文件”、“字段引用”、“来源文本片段”字段必须原样保留，不得删除或修改；
- 不要输出任何额外的文字说明；
- 不要使用 Markdown 代码块（不要输出 ```json 或 ```）；
- 在 JSON 字符串内部，禁止使用未转义的双引号。如果需要引用，用单引号代替。

请严格遵守上述要求。
"""

    user_prompt = (
        "以下是原始抽取结果列表，请进行格式规范化处理，并严格按照要求只返回一个 JSON 对象：\n\n"
        + json.dumps({"results": results_list}, ensure_ascii=False, indent=2)
    )

    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )

    raw = resp.choices[0].message.content

    # 调试用：可以先看一眼返回内容
    # print("=== Formatter 原始返回前 200 字 ===")
    # print(raw[:200])
    # print("================================")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"   ⚠️ LLM 格式规范阶段 JSON 解析失败：{e}")
        print("   返回内容前 200 字：", raw[:200])
        # 容错：出错时直接返回原结果，避免整个流程崩溃
        return results_list

    return data.get("results", results_list)
