# core/postprocess.py

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
