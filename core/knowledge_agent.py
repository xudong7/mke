# core/knowledge_agent.py
import json

def summarize_knowledge(text: str, structured_results, client, model_name: str, paper_id: str):
    system_prompt = """
你是一名材料化学研究者助手。现在需要从一篇关于介孔二氧化硅的英文文献中，
总结出可以复用的“合成规律”和“结构-性能关系”。

输入包括：
1）文献主要内容（部分或全文）；
2）该文献对应的结构化抽取结果（多个实验条件的 JSON）。

你的输出应该是一个 JSON 对象：
{
  "paper_id": "...",
  "key_findings": [
    {
      "topic": "简短中文主题",
      "summary_zh": "用中文总结该规律，指出变量和影响结果。",
      "supporting_evidence": ["相关英文原句1", "相关英文原句2"]
    },
    ...
  ]
}

注意：
- 只总结文中明确讨论、对结果有明显影响的规律；
- 不要在没有依据时猜测；
- 尽量将同一类规律归纳在一起。
"""

    user_prompt = (
        "【文献内容】:\n" + text[:6000] +
        "\n\n【结构化抽取结果】:\n" +
        json.dumps({"results": structured_results}, ensure_ascii=False, indent=2)
    )

    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0,
        response_format={"type": "json_object"}
    )
    data = json.loads(resp.choices[0].message.content)
    data["paper_id"] = paper_id
    return data
