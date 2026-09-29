# core/router.py
"""文献路由分类：soft_template_full / core_shell_simple / hard_template_simple。

修复要点（历史 bug）：
原实现把 text[:4000] 直接送给路由模型，但这些 PDF 首页被出版社版式样板占满
（实测 ACS "Just Accepted" 免责声明是【单行 4583 字】），而 CTAB/TEOS/P123 等
决定性证据位于 9900–14000 字。结果是模型只能靠标题猜，其自身 reason_zh 也承认
「文本中未提及使用表面活性剂（如CTAB）」——同一篇论文在不同运行间被判成不同类型，
进而一次误判就让整条记录被填成 "00"。

现在改为：头部摘录 + 证据片段窗口，并加入判定优先级，保证：
1) 判定证据一定进入模型视野；
2) 出现「表面活性剂 + 硅源」即判 soft_template_full（即使同时有预合成金属纳米颗粒）；
3) 证据不足时默认软模板全量抽取，绝不静默降级为全 "00"。
"""
import json
import re

# ---- 判定证据词表 ----

# 典型软模板剂（表面活性剂 / 结构导向剂）
_SURFACTANT_TERMS = (
    "ctab", "c16tab", "ctac", "pluronic", "p123", "f127", "f108",
    "block copolymer", "surfactant", "structure-directing", "structure directing",
    "brij", "tween", "sds",
)

# 硅源 / 钛源
_SILICA_SOURCE_TERMS = (
    "teos", "tmos", "tetraethyl orthosilicate", "tetramethyl orthosilicate",
    "sodium silicate", "titanium(iv) n-butoxide", "titanium tetraisopropoxide",
)

# 硬模板正面证据
_HARD_TEMPLATE_TERMS = ("hard template", "hard-template", "self-template", "self template")

# 摘录锚点：摘要 + 各类证据 + 实验章节标志
_ANCHOR_TERMS = ("abstract",) + _SURFACTANT_TERMS + _SILICA_SOURCE_TERMS + (
    "preparation of", "synthesis of", "experimental",
)


def _has_any(text_lower: str, terms) -> bool:
    return any(t in text_lower for t in terms)


def has_soft_template_evidence(text: str) -> bool:
    """是否存在「典型表面活性剂 + 硅源」的软模板正面证据。

    用于两处：路由判定优先级，以及主抽取的非破坏性兜底（误判为 simple 时升级）。
    """
    low = (text or "").lower()
    return _has_any(low, _SURFACTANT_TERMS) and _has_any(low, _SILICA_SOURCE_TERMS)


def has_hard_template_evidence(text: str) -> bool:
    """是否存在 hard template / self-template 的正面证据。"""
    return _has_any((text or "").lower(), _HARD_TEMPLATE_TERMS)


def build_router_excerpt(
    text: str,
    head: int = 1500,
    window: int = 700,
    max_windows: int = 8,
    min_gap: int = 400,
) -> str:
    """构造路由用摘录：头部（标题 + 摘要开头）+ 证据片段窗口。

    不依赖「剥除样板」（首页正文与免责声明常被解析器合并进同一行，按行剥离不可靠），
    而是直接按证据锚点取窗口，确保 CTAB/TEOS/P123/"Preparation of ..." 一定进入视野。
    """
    low = text.lower()
    positions: list[int] = []
    for term in _ANCHOR_TERMS:
        for m in re.finditer(re.escape(term), low):
            positions.append(m.start())
    positions.sort()

    picked: list[int] = []
    for p in positions:
        if len(picked) >= max_windows:
            break
        if any(abs(p - q) < min_gap for q in picked):
            continue
        picked.append(p)

    parts = [text[:head]]
    for p in picked:
        start = max(0, p - window // 3)
        parts.append(f"\n[…原文片段，位于第 {start} 字附近…]\n{text[start:start + window]}")
    return "\n".join(parts)


_SYSTEM_PROMPT = """
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

【判定优先级（非常重要，必须优先于上面的类型描述执行）】：

P1. 只要文中出现「典型表面活性剂/嵌段共聚物（CTAB、P123、F127、Pluronic、block copolymer、
    surfactant、SDA 等）+ 硅源/钛源（TEOS、TMOS、硅酸钠等）」协同组装，就【必须】判为
    soft_template_full —— 即使文中同时存在预先合成的金属纳米颗粒（Au、AuCu、Fe3O4、CdS 等）。
    把金属纳米颗粒负载/浸渍到【已经成型的介孔二氧化硅载体】上，属于负载，不是 core_shell_simple。

P2. core_shell_simple【只有在以下两条同时满足时】才可使用：
    - 预先合成的颗粒被包覆或共组装进介孔二氧化硅骨架（如 Fe3O4@nSiO2@mSiO2、CdS&mSiO2）；且
    - 文中【没有】出现「表面活性剂 + 硅源」的软模板组装描述。

P3. hard_template_simple【只有在】文中明确出现 hard template / self-template / 自模板，
    且【没有】出现「表面活性剂 + 硅源」软模板组装时才可使用。

P4. 若证据不足以确定类型，一律判为 soft_template_full（完整抽取）。
    【绝对不要】因为“没看到表面活性剂”就降级为 simple 类型 —— 那会导致整条记录被填成 "00"，
    属于最严重的数据损毁。

P5. 同一篇论文合成了多种载体/样品（如同时制备 MS、KIT-6、SBA-15、MCM-41 等）时，
    仍属于 soft_template_full（完整抽取），由后续主抽取逐步为每个样品单独记录。

P6. 输入中包含「[…原文片段…]」标记时，那些片段是同一篇文献的原文节选；
    只要片段中出现 CTAB/TEOS/P123/"Preparation of" 等，即视为该文献确实使用了软模板。

【可用 skill 名称（只能从这些名字中选择，不要编造新名字）】：
- screening_soft_template_zh
- assembly_mode_zh
- solution_and_concentrations_zh
- structure_and_properties_zh

你的任务：
1）阅读输入的英文文本（摘要 + 合成证据片段），判断 analysis_type；
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


def route_paper(text: str, client, model_name: str):
    """
    使用轻量 LLM 调用，判断分析类型 + 推荐 skills。
    输出为中文说明，并附带简单推理。
    """
    excerpt = build_router_excerpt(text or "")

    user_prompt = f"""
下面是文献的内容摘录（标题/摘要开头 + 若干原文证据片段，长度已截断）：

{excerpt}

请根据上述规则进行判断，并返回指定格式的 JSON。
注意：解释和 reason_zh 一律用中文；务必先执行「判定优先级」P1–P6 再下结论。
"""

    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
        response_format={"type": "json_object"},
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
            "source_snippets": [],
        }
