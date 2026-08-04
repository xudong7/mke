# core/structurizer_agent.py
import json

def _structurize_single_record(record, client, model_name: str):
    """
    对单条记录进行结构化，返回更新后的记录。
    """
    system_prompt = """
你是一名结构化数据解析助手。现在有一条实验记录（JSON 对象），其中包含如下人类可读字段（示例）：
- "合成温度": "40 °C 搅拌 6 h（...）"
- "比表面积": "258 m²/g（...）"
- "孔径": "6.8 nm（...）"

你的任务：
- 不要删除或修改已有字段；
- 只在该记录中增加以下结构化字段（如果有对应信息）：
  1）"合成温度_结构化": 列表，每个元素是一个阶段：
     {
       "阶段": "合成/老化/水热/干燥/焙烧 等",
       "温度值": 40,
       "温度单位": "°C",
       "时间值": 6,
       "时间单位": "h",
       "操作": "搅拌/solvothermal treatment/drying/calcination 等",
       "加热速率": 0.5,         # 可选
       "加热速率单位": "°C/min", # 可选
       "原文": "对应的英文句子"
     }

  2）"比表面积_结构化":
       [
         {
           "数值": 258,
           "单位": "m²/g",
           "方法": "BET 或其他（若可判断）",
           "样品": "样品编号（如 S1_E）",
           "原文": "对应的英文句子"
         }
       ]

  3）"孔径_结构化":
       [
         {
           "数值": 6.8,
           "单位": "nm",
           "类型": "主孔径/次孔径等（若能判断）",
           "样品": "样品编号（如 S1_E）",
           "原文": "对应的英文句子"
         }
       ]

- 如果某个字段没有可用信息，对应的 *_结构化 字段可以省略，或用 []。

输出格式必须严格是一个 JSON 对象（单条记录），结构为：
{
  "record": {
    ... 原始字段 + 新增 *_结构化 字段 ...
  }
}

禁止输出 JSON 之外的内容，禁止使用 Markdown 代码块。
在所有 JSON 字符串内部，禁止使用未转义的双引号。如果必须引用，请用单引号代替。
"""

    user_prompt = (
        "以下是一条需要结构化的实验记录，请在其中新增 *_结构化 字段：\n\n"
        + json.dumps({"record": record}, ensure_ascii=False, indent=2)
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
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"   ⚠️ 结构化单条记录 JSON 解析失败：{e}")
        print("   返回内容前 200 字：", raw[:200].replace("\n", "\\n"))
        # 出错就返回原始记录
        return record

    new_record = data.get("record", record)
    # 调试：看一下新字段
    # print("   🧱 单条记录结构化后的字段：", new_record.keys())
    return new_record


def structurize_results(results_list, client, model_name: str):
    """
    对结果列表中每一条记录分别调用 _structurize_single_record。
    """
    if not results_list:
        return results_list

    new_results = []
    for idx, r in enumerate(results_list):
        print(f"   🔧 正在结构化第 {idx+1} 条记录...")
        new_r = _structurize_single_record(r, client, model_name)
        new_results.append(new_r)

    return new_results
