"""eval/values.py —— 把自由文本变成可比对象（对齐与指标共用）。

只负责「解析与归一」，不负责判定；判定规则见 eval/metrics.py，口径见 eval/schema.yaml。
"""
from __future__ import annotations

import re

from .config import MISSING_TOKENS

# ---------------------------------------------------------------- 基础归一

_WS = re.compile(r"\s+")
_SUBS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_SUPS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_FULL = str.maketrans("（），；：％－～", "(),;:%-~")


def norm_text(v) -> str:
    if v is None:
        return ""
    s = str(v)
    s = s.translate(_SUBS).translate(_SUPS).translate(_FULL)
    s = s.replace("℃", "°C").replace("oC", "°C").replace("° C", "°C")
    s = _WS.sub(" ", s).strip().lower()
    return s


def is_missing(v) -> bool:
    """缺失判定：空 / 00 / — / null 等统一视为缺失（见 schema.yaml 的 missing）。"""
    if v is None:
        return True
    if isinstance(v, (list, dict)):
        return len(v) == 0
    return norm_text(v) in MISSING_TOKENS


# ---------------------------------------------------------------- 数值

_NUM = re.compile(r"(\d+(?:\.\d+)?)")


def number_near_unit(v, unit_pattern: str) -> float | None:
    """取「贴着单位」的那个数值；没有则退到首个数值。

    例：'281 m²/g（MCM-48/DPA-OTf [4]: 281 m2/g）' → 281.0
        '1.4 nm（...）' → 1.4；'>1000' → 1000.0；'ca. 3' → 3.0
    """
    if is_missing(v):
        return None
    s = norm_text(v)
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:" + unit_pattern + ")", s):
        return float(m.group(1))
    m = _NUM.search(s)
    return float(m.group(1)) if m else None


def first_number(v) -> float | None:
    if is_missing(v):
        return None
    m = _NUM.search(norm_text(v))
    return float(m.group(1)) if m else None


def temperature_set(v) -> set[float]:
    """抽取全部温度值（°C）。'80 °C老化4 h；450 °C焙烧' → {80.0, 450.0}"""
    if is_missing(v):
        return set()
    s = norm_text(v)
    return {float(m.group(1)) for m in re.finditer(r"(\d+(?:\.\d+)?)\s*°c", s)}


# ---------------------------------------------------------------- 实体

SURFACTANTS: dict[str, tuple[str, ...]] = {
    "P123": ("p123", "pluronic p123", "eo20po70eo20"),
    "F127": ("f127", "pluronic f127", "eo106po70eo106"),
    "F108": ("f108", "pluronic f108"),
    "P103": ("p103", "pluronic p103"),
    "P105": ("p105", "pluronic p105"),
    "CTAB": ("ctab", "c16tma", "c16tab", "十六烷基三甲基溴化铵", "cetyltrimethylammonium"),
    "C12TMA": ("c12tma", "dtab", "十二烷基三甲基溴化铵", "dodecyltrimethylammonium"),
    "C16TMAOH": ("c16tmaoh",),
    "TMB": ("tmb", "1,3,5-trimethylbenzene", "均三甲苯", "trimethylbenzene"),
    "TEA": ("三乙醇胺", "triethanolamine"),
    "Brij": ("brij", "聚氧乙烯月桂醚"),
    "Tween": ("tween", "吐温"),
    "SDS": ("sds", "十二烷基硫酸钠"),
}

SILICA_SOURCES: dict[str, tuple[str, ...]] = {
    "TEOS": ("teos", "tetraethyl orthosilicate", "四乙氧基硅烷", "正硅酸乙酯", "tetraethoxysilane"),
    "TMOS": ("tmos", "tetramethyl orthosilicate", "四甲氧基硅烷", "正硅酸甲酯"),
    "Triethoxysilane": ("triethoxysilane", "三乙氧基硅烷"),
    "硅酸钠": ("硅酸钠", "sodium silicate", "water glass"),
    "硅酸盐": ("硅酸盐", "silicate"),
    "fumed silica": ("fumed silica", "气相二氧化硅"),
    "Ti source": ("titanium", "ti(onbu)4", "ti(oipr)4", "钛"),
}

SALTS: dict[str, tuple[str, ...]] = {
    "NaCl": ("nacl", "氯化钠"),
    "NaI": ("nai", "碘化钠"),
    "KCl": ("kcl", "氯化钾"),
    "KBr": ("kbr", "溴化钾"),
    "NaF": ("naf", "氟化钠"),
    "Na2SO4": ("na2so4", "硫酸钠"),
    "NaNO3": ("nano3", "硝酸钠"),
    "NH4NO3": ("nh4no3", "硝酸铵"),
    "NaAc": ("ch3coona", "乙酸钠", "sodium acetate"),
    "CaCl2": ("cacl2", "氯化钙"),
}

ACIDS_BASES: dict[str, tuple[str, ...]] = {
    "HCl": ("hcl", "盐酸", "hydrochloric"),
    "NaOH": ("naoh", "氢氧化钠"),
    "NH4OH": ("nh4oh", "氨水", "ammonium hydroxide", "氨"),
    "TEA": ("三乙醇胺", "triethanolamine"),
    "HNO3": ("hno3", "硝酸"),
    "H2SO4": ("h2so4", "硫酸"),
    "H3PO4": ("h3po4", "磷酸"),
    "AcOH": ("acetic acid", "乙酸", "醋酸"),
    "Na2CO3": ("na2co3", "碳酸钠"),
    "pH": ("ph",),
}

SOLVENTS: dict[str, tuple[str, ...]] = {
    "H2O": ("h2o", "water", "水", "去离子水", "di water"),
    "EtOH": ("ethanol", "etoh", "乙醇"),
    "BuOH": ("butanol", "buoh", "丁醇"),
    "iPrOH": ("2-propanol", "isopropanol", "异丙醇"),
    "MeOH": ("methanol", "甲醇"),
    "THF": ("thf", "四氢呋喃"),
    "toluene": ("toluene", "甲苯"),
    "hexane": ("hexane", "己烷"),
    "cyclohexane": ("cyclohexane", "环己烷"),
}


def _find(lexicon: dict[str, tuple[str, ...]], s: str) -> set[str]:
    hits = set()
    for canon, keys in lexicon.items():
        for k in keys:
            if k in s:
                hits.add(canon)
                break
    return hits


_UNIT_TOKENS = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mg/ml|wt%|w%|g/ml|mol/l|mmol/g|m2/g|m²/g|nm|ml|µl|ul|l\b|mg|g\b|mol|h\b|min|°c)",
    re.IGNORECASE,
)


def unit_tokens(v) -> set[str]:
    """数值 + 单位 的归一 token，例如 '4.5 mL' → '4.5ml'。"""
    if is_missing(v):
        return set()
    s = norm_text(v)
    out = set()
    for m in _UNIT_TOKENS.finditer(s):
        unit = m.group(2).lower().replace("²", "2")
        num = m.group(1).rstrip("0").rstrip(".") if "." in m.group(1) else m.group(1)
        out.add(f"{num}{unit}")
    return out


def entity_tokens(field_key: str, v) -> set[str]:
    if is_missing(v):
        return set()
    s = norm_text(v)
    lexicon = {
        "表面活性剂": SURFACTANTS,
        "硅源/浓度": SILICA_SOURCES,
        "盐种类/浓度": SALTS,
        "酸/碱浓度": ACIDS_BASES,
        "合成溶液体系（体积比）": SOLVENTS,
    }.get(field_key, {})
    return _find(lexicon, s) if lexicon else set()


def token_set(field_key: str, v) -> set[str]:
    """字段级比较用的 token 集合 = 实体 + 数值单位。"""
    return entity_tokens(field_key, v) | unit_tokens(v)


# ---------------------------------------------------------------- 枚举归一

# 顺序即优先级：「溶胶-凝胶」是明确的路线名，要先于酸碱细分命中，
# 否则「溶胶-凝胶法（酸性体系）」会被误归到「软模板-酸性」，与 gold 的「溶胶-凝胶」对不上。
_ASSEMBLY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("溶胶-凝胶", ("溶胶-凝胶", "sol-gel", "共缩合", "co-condensation", "condensation")),
    ("硬模板-自模板", ("硬模板", "自模板", "aao", "铸型", "nanocasting", "hard templat", "carbon templat")),
    ("软模板-碱性", ("碱性", "碱催化", "naoh", "nh4oh", "氨水", "ammonium hydroxide")),
    ("软模板-酸性", ("酸性", "hcl", "盐酸", "acidic")),
    ("软模板-未标酸碱", ("软模板", "胶束", "液晶", "模板法", "micelle", "templating")),
)

_STRUCTURE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("2D 六方", ("p6mm", "hexagonal", "六方", "mcm-41", "sba-15", "2d hex")),
    ("3D 立方", ("cubic", "立方", "im3m", "ia3d", "sba-16", "mcm-48", "kit-6", "bicontinuous")),
    ("3D 六方", ("3d hex",)),
    ("蠕虫状", ("worm", "蠕虫")),
    ("层状", ("lamellar", "层状")),
    ("无序", ("disordered", "无序", "wormlike")),
    ("非介孔", ("非介孔", "non-porous", "nonporous", "无孔")),
)


def enum_group(field_key: str, v) -> str | None:
    if is_missing(v):
        return None
    s = norm_text(v)
    rules = _ASSEMBLY_RULES if field_key == "组装方式" else _STRUCTURE_RULES if field_key == "产物介孔结构" else ()
    for name, keys in rules:
        if any(k in s for k in keys):
            return name
    return "其他"


# ---------------------------------------------------------------- 宽松文本

_STOP = set("的 了 和 与 在 是 为 及其 以及 约 大约 得到 可 能 使用 采用".split())


def keywords(v) -> set[str]:
    """产物形态这类自由描述的宽松关键词（中文按 2-gram，英文按词）。"""
    if is_missing(v):
        return set()
    s = norm_text(v)
    out: set[str] = set()
    for w in re.findall(r"[a-z]{4,}", s):
        if w not in _STOP:
            out.add(w)
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", s):
        for i in range(len(chunk) - 1):
            out.add(chunk[i : i + 2])
    return out
