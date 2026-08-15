# core/extractor.py
import json
import time
from pathlib import Path
from openai import OpenAI

from .citation_agent import add_field_sentence_citations_for_paper
from .prompt_builder import build_prompt_zh
from .router import route_paper


def truncate_references(text: str) -> str:
    ref_keywords = ["References", "REFERENCES", "Bibliography", "参考文献"]
    for kw in ref_keywords:
        if kw in text:
            return text.split(kw)[0]
    return text


class MesoporousExtractor:
    def __init__(self, api_key: str, base_url: str, model_name: str, skill_manager):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name
        self.skill_manager = skill_manager

    def extract_from_text(self, text: str, routing: dict | None = None):
        """
        对单篇文献文本进行抽取，返回 JSON 中的 results 列表。

        routing: 可选。传入已由 route_paper 算好的路由结果时跳过重新路由，
                 便于后端将"路由"与"主抽取"拆成两个独立步骤。
        """
        if not text or len(text.strip()) < 100:
            return []

        text = truncate_references(text)

        # A0：路由 agent（传入 routing 时不再调用 LLM 路由）
        routing = routing if routing is not None else route_paper(text, self.client, self.model_name)
        analysis_type = routing.get("analysis_type", "soft_template_full")
        selected_skills = routing.get("selected_skills", [])
        route_reason = routing.get("reason_zh", "")
        route_snippets = routing.get("source_snippets", [])
        route_snippets_str = " / ".join(route_snippets)

        # 分支一：core_shell 或 hard_template，走简化抽取
        if analysis_type in ("core_shell_simple", "hard_template_simple"):
            results = self._simple_record_extract(text, analysis_type)
        else:
            # 分支二：正常软模板全量抽取
            if not selected_skills:
                selected_skills = [
                    "screening_soft_template_zh",
                    "assembly_mode_zh",
                    "solution_and_concentrations_zh",
                    "structure_and_properties_zh",
                ]

            skill_prompt_blocks = self.skill_manager.get_prompt_blocks(selected_skills)
            system_prompt, user_prompt = build_prompt_zh(text, skill_prompt_blocks)

            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0,
                    response_format={"type": "json_object"}
                )
                content = response.choices[0].message.content
                try:
                    data = json.loads(content)
                except json.JSONDecodeError as e:
                    print(f"   ⚠️ 主抽取阶段 JSON 解析失败：{e}")
                    print("   返回内容前 200 字：", content[:200])
                    return []
                results = data.get("results", [])
            except Exception as e:
                print(f"   ⚠️ API 处理出错: {e}")
                return []

        # 统一附加：分析类型 + 路由推理 + 来源文本片段
        for r in results:
            r.setdefault("分析类型", self._map_analysis_type_to_zh(analysis_type))

            if "推理说明" in r and r["推理说明"] != "00":
                r["推理说明"] = f"[路由判断] {route_reason}；[细节推理] {r['推理说明']}"
            else:
                r["推理说明"] = f"[路由判断] {route_reason}"

            if not r.get("来源文本片段") or r["来源文本片段"] == "00":
                r["来源文本片段"] = route_snippets_str or "00"

        return results

    def _map_analysis_type_to_zh(self, analysis_type: str) -> str:
        if analysis_type == "soft_template_full":
            return "软模板法，完整分析"
        if analysis_type == "core_shell_simple":
            return "预合成纳米颗粒复合结构，仅简单记录"
        if analysis_type == "hard_template_simple":
            return "自模板/硬模板，仅记录方法"
        return "00"

    def _simple_record_extract(self, text: str, analysis_type: str):
        """
        给 core_shell_simple / hard_template_simple 用的简化版 agent。
        """
        system_prompt = """
你是一名材料化学专家。现在只需要做“简化记录”，而不是完整抽取。
请阅读英文文献内容，根据说明输出 JSON：

1）若 analysis_type = "core_shell_simple"：
   - 判断复合物的组成（介孔二氧化硅-某物质，如 Fe3O4、CdS 等），写入字段“组成”；
   - 判断结构形貌（core@shell, Janus, asymmetric 等），写入字段“结构”；
   - 其他字段统一填 "00"；
   - 在“分析类型”字段写："预合成纳米颗粒复合结构，仅简单记录"。

2）若 analysis_type = "hard_template_simple"：
   - 判断合成方法属于“自模板”或“硬模板”，写入字段“组装方式”； 
   - 其他字段统一填 "00"；
   - 在“分析类型”字段写："自模板/硬模板，仅记录方法"。

输出格式固定为：
{ "results": [ { 各字段... } ] }
字段至少包括：
- 分析类型
- 组装方式
- 组成
- 结构
- 溶剂体系
- pH值_酸碱浓度
- 表面活性剂种类
- 表面活性剂浓度
- 硅/钛源种类_浓度
- 盐种类_浓度
- 合成温度
- 介孔结构
- 比表面积
- 孔径
- 产物形态
- 其他变量
若无数据则填 "00"。
"""
        user_prompt = f"analysis_type = {analysis_type}\n\n英文文献内容如下：\n\n{text}"

        try:
            resp = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0,
                response_format={"type": "json_object"}
            )
            data = json.loads(resp.choices[0].message.content)
            results = data.get("results", [])
            return results
        except Exception as e:
            print(f"   ⚠️ 简化抽取出错: {e}")
            return []

    def batch_process_md_dir(self, input_dir: Path, sleep_sec: float = 0.5):
        """
        扫描文件夹下所有 .md，逐个抽取，返回所有结果列表及 file_name 信息。
        """
        md_files = list(Path(input_dir).rglob("*.md"))
        print(f"📂 发现 {len(md_files)} 个 .md 文件，准备开始抽取...\n")

        all_results = []

        for idx, md_file in enumerate(md_files):
            print(f"[{idx+1}/{len(md_files)}] 正在处理: {md_file.name} ...")
            try:
                content = md_file.read_text(encoding="utf-8")
                truncated = truncate_references(content)
                # 1) 主抽取
                results = self.extract_from_text(truncated)
                # 2) 字段级整句引用 agent
                results = add_field_sentence_citations_for_paper(
                    text=truncated,
                    structured_results=results,
                    client=self.client,
                    model_name=self.model_name,
                )

                if results:
                    for r in results:
                        # 这里你也可以换成 md_file.name，看你需求
                        r["来源文件"] = md_file.parent.name
                        all_results.append(r)
                    print(f"   ✅ 成功提取 {len(results)} 条实验数据")
                else:
                    print("   ❓ 未能在该文件中找到有效数据")
                time.sleep(sleep_sec)
            except Exception as e:
                print(f"   ❌ 读取文件失败: {md_file.name}, 错误: {e}")

        return all_results
