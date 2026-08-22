# 介孔材料文献知识自动抽取系统

基于**大模型智能体**的材料化学文献知识抽取系统:给定一篇化学材料文献(当前聚焦介孔材料,尤其是介孔二氧化硅及其复合物),自动抽取高质量的**结构化实验知识**。

## 功能特性

- **多 agent 流水线**:路由判断 → 主抽取 → 字段级引用标注 → 结构化,每个阶段由一次独立的 LLM 调用承担一个角色
- **路由分层抽取**:自动区分「软模板法(全量详细抽取)」「预合成纳米颗粒复合结构(仅记录组成/结构)」「自模板/硬模板(仅记录方法)」,按需分配抽取深度,节省 token
- **技能模块化**:抽取规则拆分为 5 个可组合的 skill(`skills/*.json`),由路由动态装配
- **可溯源**:每个字段附英文原文短语,另有「字段引用」完整句子回标与「推理说明」
- **多记录原则**:表格每一行、每个样品独立成一条记录,禁止范围合并
- **数值结构化**:合成温度/比表面积/孔径被拆分为机器可读的 `*_结构化` 字段(数值+单位+样品+原文)
- **结果导出**:JSONL / pretty JSON / Excel 三种格式

## 快速开始

依赖管理使用 [uv](https://docs.astral.sh/uv/)(Python ≥ 3.10):

```bash
# 1. 安装依赖(自动创建 .venv 与 uv.lock)
uv sync

# 2. 配置环境变量(密钥不会入库)
cp .env.example .env
#   编辑 .env,填入 OPENAI_API_KEY

# 3. 运行批量抽取
uv run python main.py
```

## 配置说明

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 无(必填) | API 密钥,可从 `.env` 或 shell 环境读取 |
| `OPENAI_BASE_URL` | `https://api.deepseek.com` | API 端点,默认 DeepSeek |
| `MODEL_NAME` | `deepseek-chat` | 模型名称 |

`config.py` 中的开关:

- `USE_LLM_FORMATTER`:是否启用 LLM 格式规范化阶段(当前关闭)
- `USE_STRUCTURIZER`:是否启用数值结构化阶段(当前开启)

## 输入与输出

**输入**:`data/new_papers_info-100/` 下每篇文献一个文件夹,内含 PDF 转出的全文 `content.md`。

**输出**:`data/outputs/` 下按运行时间戳生成

- `raw_results_*.jsonl` / `raw_results_pretty_*.json` — 抽取原始结果
- `normalized_results_*.jsonl` / `normalized_results_pretty_*.json` — 规范化(含 `*_结构化` 字段)
- `介孔材料批量抽取结果.xlsx` — Excel 汇总

> `data/` 目录(文献全文与输出)不纳入 git 版本管理,请通过其他渠道备份。

## Web 界面

系统附带一个 Web 界面(黑白灰主题,红黄绿仅用于状态信号),三栏可折叠布局:

- **左栏**:已上传 PDF 论文列表 + 上传按钮 + 每篇论文的**历史解析结果**(查看/重新运行,可折叠)
- **中栏**:PDF 论文浏览器 — pdf.js 渲染(devicePixelRatio 高清/缩放/适应宽度/翻页),语料库中无 PDF 的论文为文本预览
- **右栏**:解析流程**横向时间轴看板** — ① PDF 解析(本地版面重建:两栏排序/页眉页脚过滤) → ② 路由分类 → ③ 主抽取 → ④ 字段引用 → ⑤ 数值结构化,点击节点查看该步中间结果;下方结果表支持**结果批注**(行/字段级,挂载于运行记录,不修改原结果),可折叠

**运行历史**:每次执行流水线自动保存到后端(`data/runs/`),刷新/跳转不丢失;可从左侧历史选择查看任意一次运行结果,或一键重新运行(新开记录)。

```bash
# 1. 启动后端(FastAPI,默认 :8000)
uv run uvicorn backend.main:app --reload --port 8000

# 2a. 开发模式(前端热更新,:5173, /api 自动代理)
cd frontend && npm install && npm run dev

# 2b. 生产模式(构建产物由后端单端口托管,:8000)
cd frontend && npm run build && open http://localhost:8000
```

> ②–⑤ 步调用 LLM,消耗 API token;PDF 解析为纯本地计算。

## 目录结构

```
demo/
├── main.py                  # 入口:批量处理 → 规范化 → 导出(CLI)
├── config.py                # 路径与模型配置(密钥走环境变量)
├── core/
│   ├── extractor.py         # 主抽取器:路由分发 + 批量处理
│   ├── router.py            # Agent① 文献分类路由,推荐 skills
│   ├── prompt_builder.py    # 基础抽取提示词(字段规范、多记录规则)
│   ├── skills_manager.py    # 技能加载与提示词块拼装
│   ├── citation_agent.py    # Agent③ 字段级整句引用标注
│   ├── formatter_agent.py   # Agent④ 格式规范化(可选)
│   ├── structurizer_agent.py# Agent⑤ 数值结构化(逐条调用)
│   ├── postprocess.py       # 规则格式化:补全字段,缺失填 "00"
│   └── knowledge_agent.py   # Agent⑥ 合成规律/结构-性能关系总结(待接线)
├── backend/                 # Web API(FastAPI)
│   ├── main.py              # 入口:CORS、路由挂载、生产模式静态托管(SPA fallback)
│   ├── deps.py              # 路径常量与惰性 OpenAI 客户端(不 import config.py)
│   ├── parser.py            # PDF 轻量版面重建(PyMuPDF):栏检测/页眉页脚过滤
│   ├── papers.py            # 论文列表 / 全文 / PDF 服务 / 上传解析
│   ├── pipeline.py          # 流水线 5 步无状态端点(parse/route/extract/cite/structurize)
│   ├── runs.py              # 运行历史持久化(JSON 文件,data/runs/)
│   ├── annotations.py       # 结果批注 CRUD(挂 run,data/annotations/)
│   └── smoke_test.py        # 后端冒烟测试脚本
├── frontend/                # Web 前端(React 18 + Vite + TS)
│   ├── src/
│   │   ├── components/paper/      # 论文列表 / pdf.js 阅读器 / 文本预览 / 运行历史
│   │   ├── components/pipeline/   # 时间轴看板 / 结果表格(可批注)
│   │   ├── components/annotation/ # 结果批注面板
│   │   └── hooks/                 # usePipeline(运行同步) / useAnnotations
│   └── e2e/                 # Playwright 端到端验证脚本
├── skills/                  # 可组合的技能模块(JSON)
├── data/                    # 输入文献与输出结果(git 忽略)
└── pyproject.toml / uv.lock # uv 依赖管理
```

## 抽取字段

组装方式、溶剂体系、pH值_酸碱浓度、表面活性剂种类/浓度、硅/钛源种类_浓度、盐种类_浓度、合成温度、介孔结构、比表面积、孔径、产物形态、其他变量、来源文本片段、推理说明、字段引用。

## 已知待办

- `knowledge_agent.py` 已实现但未接入管线(总结可复用的合成规律与结构-性能关系)
- `router` / `citation_agent` 对输入文本有长度截断(4000/8000 字符),长文献的方法与表格段可能丢失
- 每次 LLM 调用无重试机制,偶发解析失败会静默丢弃整篇文献
