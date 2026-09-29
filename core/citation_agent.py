# core/citation_agent.py
import json

from .json_utils import loads_lenient

def add_field_sentence_citations_for_paper(
    text: str,
    structured_results,
    client,
    model_name: str,
):
    """
    为同一篇文章的一批 structured_results 添加字段级整句引用：
    每条记录增加一个 '字段引用' 字段，其结构为：
    {
      "组装方式": ["完整英文句子1", "完整英文句子2", ...],
      "溶剂体系": ["..."],
      ...
    }
    """
    if not structured_results:
        return structured_results

    system_prompt = """
你是一名文献标注助手。输入包括：
1）一篇英文文献的主要内容；
2）从该文献中抽取出的若干条结构化记录（每条记录包含多个字段：组装方式、溶剂体系、pH值_酸碱浓度、表面活性剂种类等）。

你的任务：
- 对每一条记录的每一个主要字段，在原文中查找和该字段最相关的【完整英文句子】，而不是短语；
- 每个字段可以对应 1-3 条英文句子，它们应当整体上支持该字段的中文内容；
- 如果某个字段在原文中找不到明显对应的句子，可以不给该字段添加引用。

需要重点关注并尝试添加引用的字段包括（字段名为中文）：
- "组装方式"
- "溶剂体系"
- "pH值_酸碱浓度"
- "表面活性剂种类"
- "表面活性剂浓度"
- "硅/钛源种类_浓度"
- "盐种类_浓度"
- "合成温度"
- "介孔结构"
- "比表面积"
- "孔径"
- "产物形态"
- "其他变量"

输出格式必须严格是一个 JSON 对象：
{
  "results": [
    {
      "index": 0,
      "field_citations": {
        "组装方式": ["完整英文句子1.", "完整英文句子2."],
        "溶剂体系": ["..."],
        ...
      }
    },
    {
      "index": 1,
      "field_citations": { ... }
    }
  ]
}

注意：
- index 对应输入 structured_results 的列表索引（从 0 开始）；
- 每个字段的引用应为完整句子（以句号或分号结尾），不要只给 very 短的 phrase；
- 如果找不到某个字段的来源，可以不写该字段的 key，或让其值为 []；
- 禁止输出 JSON 之外的内容，禁止使用 Markdown 代码块。
"""

    user_prompt = (
        "【文献内容】:\n" + text[:8000] +
        "\n\n【结构化抽取结果】:\n" +
        json.dumps({"results": structured_results}, ensure_ascii=False, indent=2)
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
    try:
        data = loads_lenient(raw)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"   ⚠️ 字段整句引用 agent JSON 解析失败：{e}")
        print("   返回内容前 200 字：", raw[:200])
        return structured_results

    mapping_list = data.get("results", [])
    for m in mapping_list:
        idx = m.get("index")
        field_citations = m.get("field_citations", {})
        if isinstance(idx, int) and 0 <= idx < len(structured_results):
            structured_results[idx]["字段引用"] = field_citations

            # 可选：如果你希望“来源文本片段”也用整句替代，可以这样：
            if field_citations:
                merged_sentences = []
                for sent_list in field_citations.values():
                    merged_sentences.extend(sent_list)
                # 去重
                merged_sentences = list(dict.fromkeys(merged_sentences))
                structured_results[idx]["来源文本片段"] = " ".join(merged_sentences)

    return structured_results
