# core/json_utils.py
"""LLM 返回内容的容错 JSON 解析。

背景：即使设置了 response_format={"type":"json_object"}，模型偶尔仍会在完整 JSON
之后追加多余内容（实测报错 "Extra data: line 1 column 4929"），导致整条记录被丢弃、
静默失去 *_结构化 字段。这里先直接解析，失败则截取第一个括号平衡的 JSON 对象再解析。
"""
import json


def loads_lenient(raw: str):
    """解析 LLM 返回的 JSON；容忍前后多余文本。失败时抛原始异常。"""
    if raw is None:
        raise ValueError("empty response")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    if start < 0:
        raise ValueError(f"no JSON object found in response: {raw[:200]!r}")

    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(raw[start:i + 1])

    # 括号未闭合：交给原始解析器抛出可读错误
    return json.loads(raw[start:])
