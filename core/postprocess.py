# core/postprocess.py
"""抽取结果后处理：字段补全 + 空记录剔除 + 重复样品合并。

背景（历史 bug）：system prompt 里「多组样品必须逐条记录、不允许合并」的规则过于强势，
LLM 会把同一材料在摘要/正文/结论中的多次提及、以及仅在图表中出现的样品编号，
全部枚举成独立记录，于是产生大量除 "00" 外没有任何数据的空记录。
实测《介孔文献10》一次抽取返回 16 条，其中 12 条为纯空记录，真正的样品只有 4 条。

这里用确定性的后处理兜底，不依赖 LLM 的稳定性。
"""
import re

# 参与「记录是否有内容」判定的字段
_CONTENT_FIELDS = [
    "组装方式", "溶剂体系", "pH值_酸碱浓度", "表面活性剂种类", "表面活性剂浓度",
    "硅/钛源种类_浓度", "盐种类_浓度", "合成温度", "介孔结构", "比表面积",
    "孔径", "产物形态", "其他变量", "组成", "结构",
]

# 判定「该记录是否包含合成配方信息」的字段：至少一个非空，才作为合成记录保留。
# 论文里常有「只给了组成/结构、没有合成条件」的样品（例如同一载体上不同 Au 负载量的
# 系列催化剂）。它们不是合成配方，按需求过滤掉，避免结果里出现大片 "00" 的行。
_SYNTHESIS_FIELDS = [
    "组装方式", "溶剂体系", "pH值_酸碱浓度", "表面活性剂种类", "表面活性剂浓度",
    "硅/钛源种类_浓度", "盐种类_浓度", "合成温度",
]

# 判定「样品身份」的字段：必须是全部内容字段。
# 曾只用 8 个配方字段，导致「配方字段全空但其他变量各不相同」的记录
# （例如同一载体上 Au 负载量 1/3/6 wt.-% 的系列样品）被误判为重复而互相覆盖，
# 一次就丢掉了 11 个样品。只有全部内容字段都一致才算真正的重复。
_FINGERPRINT_FIELDS = _CONTENT_FIELDS

_EMPTY_VALUES = {"", "00", "-", "--", "n/a", "none", "null", "未提及", "未说明"}


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return str(value).strip().lower() in _EMPTY_VALUES


def _has_content(record: dict) -> bool:
    """只要任一内容字段非空，该记录就保留。

    注意：不能要求「所有字段都填满」——按 prompt 规则，只给出部分信息的样品
    （例如只有孔径、没有比表面积）也应当单独记录。
    """
    return any(not _is_empty(record.get(f)) for f in _CONTENT_FIELDS)


def _fingerprint(record: dict) -> tuple:
    """配方指纹：去掉括号内的英文原文，只比较中文/数值主体。

    同一配方的英文摘录在不同记录里可能不同，因此不能直接比对原字符串。
    """
    parts = []
    for field in _FINGERPRINT_FIELDS:
        value = record.get(field)
        if _is_empty(value):
            parts.append("")
            continue
        core = re.split(r"[（(]", str(value))[0]      # 去掉「（英文原文）」
        parts.append(re.sub(r"\s+", "", core).lower())
    return tuple(parts)


def _merge_records(records: list) -> dict:
    """合并同一配方的多条记录：取字段最丰富的一条，补齐缺失字段，合并字段引用。"""
    best = max(
        records,
        key=lambda r: sum(1 for f in _CONTENT_FIELDS if not _is_empty(r.get(f))),
    )
    merged = dict(best)

    # 只填补 "00" 空位，绝不覆盖已有值
    for field in _CONTENT_FIELDS:
        if _is_empty(merged.get(field)):
            for r in records:
                if not _is_empty(r.get(field)):
                    merged[field] = r[field]
                    break

    # 字段引用取并集（去重、保持顺序）
    # 注意：citation 步骤之前 simple_format_results 会把缺失字段填成字符串 "00"，
    # 所以这里必须先确认是 dict 再遍历。
    citations: dict[str, list] = {}
    for r in records:
        field_refs = r.get("字段引用")
        if not isinstance(field_refs, dict):
            continue
        for field, sentences in field_refs.items():
            if not isinstance(sentences, list):
                continue
            bucket = citations.setdefault(field, [])
            for s in sentences:
                if s not in bucket:
                    bucket.append(s)
    if citations:
        merged["字段引用"] = citations

    return merged


def _has_synthesis_info(record: dict) -> bool:
    """是否包含至少一项合成条件（组装方式/温度/表面活性剂/硅源等）。"""
    return any(not _is_empty(record.get(f)) for f in _SYNTHESIS_FIELDS)


def cleanup_results(results_list: list, require_synthesis: bool = False) -> list:
    """剔除全空记录 + 合并同一配方的重复记录。

    require_synthesis 默认 False：保留「只有组成/结构、没有合成条件」的样品记录。
    这类记录对应论文真实的样品（如同一载体上不同 Au 负载量的系列），不应丢弃；
    它们的合成列为 "00" 属于抽取器未抓到负载/后处理步骤，是另一个待修的问题。

    设为 True 可切换为「只保留含合成条件的记录」——保留为可选策略开关。
    """
    if not results_list:
        return []

    kept = [r for r in results_list if _has_content(r)]
    dropped = len(results_list) - len(kept)

    no_recipe = 0
    if require_synthesis:
        recipe_kept = [r for r in kept if _has_synthesis_info(r)]
        no_recipe = len(kept) - len(recipe_kept)
        if kept and not recipe_kept:
            print(f"   ⚠️ {len(kept)} 条记录均无合成条件（只有组成/结构），已全部过滤。")
        kept = recipe_kept

    groups: dict[tuple, list] = {}
    order: list[tuple] = []
    for r in kept:
        fp = _fingerprint(r)
        if fp not in groups:
            groups[fp] = []
            order.append(fp)
        groups[fp].append(r)

    merged_list = []
    merged_away = 0
    for fp in order:
        bucket = groups[fp]
        if len(bucket) == 1:
            merged_list.append(bucket[0])
        else:
            merged_away += len(bucket) - 1
            merged_list.append(_merge_records(bucket))

    if dropped or merged_away or no_recipe:
        print(
            f"   🧹 结果清理：剔除全空记录 {dropped} 条，"
            f"过滤非合成记录 {no_recipe} 条，"
            f"合并重复样品 {merged_away} 条，保留 {len(merged_list)} 条"
        )
    return merged_list


def simple_format_results(results_list):
    """
    目前先做简单处理：
    - 确保所有字段存在，不存在的填 '00'
    - 为未来更复杂的合并/冲突消解预留接口
    """
    if not results_list:
        return []

    # 想要的字段列表（和 system prompt 中定义的一致）
    fields = [
        "来源文件",
        "分析类型",
        "组装方式",
        "溶剂体系",
        "pH值_酸碱浓度",
        "表面活性剂种类",
        "表面活性剂浓度",
        "硅/钛源种类_浓度",
        "盐种类_浓度",
        "合成温度",
        "介孔结构",
        "比表面积",
        "孔径",
        "产物形态",
        "其他变量",
        "来源文本片段",
        "推理说明",
        "字段引用",
    ]

    formatted = []
    for r in results_list:
        new_r = {}
        for f in fields:
            new_r[f] = r.get(f, "00")
        formatted.append(new_r)
    return formatted
