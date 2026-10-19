# eval —— 评测尺子（怎么跑、怎么验）

口径文档：[DESIGN.md](DESIGN.md)（评测规则）｜[schema.yaml](schema.yaml)（字段口径）
方法总纲：《验证策略.md》（三级证据模型 + 尺子自检）

## 一次性跑全套

```bash
cd mke
uv run python -m eval.golden            # 1. 人工标注 → eval/data/golden.jsonl
uv run python -m eval.predictions --latest   # 2. data/runs → eval/data/predictions.jsonl
uv run python -m eval.tests.test_metrics     # 3. 尺子自身的单元测试
uv run python -m eval.selftest          # 4. 阳性对照（必须 100%）
uv run python -m eval.ablate            # 5. 阴性对照（必须全部 PASS）
uv run python -m eval.run_eval          # 6. 出 eval/report.md
```

任何一步非 0 退出码，就是这一步没实现好，别往下走。

> 依赖：`xlrd`（读 BIFF8 的 .xls）。它是 1 号的 Stage 0 要加进 `[dependency-groups].dev` 的；
> 在他加之前，本地用 `uv pip install --python .venv/Scripts/python.exe xlrd` 临时装上即可。

## 每个功能怎么检测

### 1. gold 清洗（`eval/golden.py`）

```bash
uv run python -m eval.golden
```

**通过标准**（会自己判）：

- 行型统计出现 `编号行 233 / 续行 31 / 注释行:备注 16 / 注释行:计算过程 215 / 全空杂行 1`
- `记录合计 264`、`覆盖论文数 100`，末行打印 `原始表口径：与 DESIGN 2.1 一致`
- 默认排除文献32/36/46（DESIGN 2.2），写出 `eval/data/golden.jsonl` **261 行 / 97 篇**，
  字段填充率约 87.9%；需要要回那 3 篇时加 `--keep-excluded`

**失败信号**：原始表口径不是 264 → 行型规则被改动或原表变了，先别用这份数据算指标。

### 2. 预测导出（`eval/predictions.py`）

```bash
uv run python -m eval.predictions --latest
```

**通过标准**：打印覆盖论文数与记录合计；`--latest` 下同一篇论文只保留最新 run（不加会重复计入）。
现阶段应看到 3 篇（文献10/14/15）。

**怎么单独确认某一篇**：`data/runs/<run_id>.json` 里 `paper_id` 与 `records` 都在，
`eval/data/predictions.jsonl` 每行就是一条 run，可直接 diff。

### 3. 尺子本身（单测 + 阳/阴对照）——**这一步最重要**

```bash
uv run python -m eval.tests.test_metrics   # 期望：5 组用例，0 条失败
uv run python -m eval.selftest             # 期望：记录匹配率 100%、字段 F1 100%
uv run python -m eval.ablate               # 期望：6 条断言全 PASS
```

三者分别在验：

| 命令 | 在验什么 | 通过标准 |
| --- | --- | --- |
| `test_metrics` | 五态判定 / 容差边界 / 缺失语义 / 抽错双计 | 0 失败 |
| `selftest`（阳性对照） | 把 golden 当预测喂进去，尺子会不会自己判满分 | F1 = 100%、匹配率 = 100% |
| `ablate`（阴性对照） | 故意注入缺陷，分数会不会按预期下降 | 6 条断言全 PASS |

`ablate` 的 6 条断言对应的期望：

| 注入的缺陷 | 期望反应 |
| --- | --- |
| 完整（阳性对照） | 满分 |
| 比表面积整列清成 00 | 该字段 F1 → 0 |
| 比表面积/孔径 数值 ×2 | 比表面积 F1 大幅下降（<10%） |
| 每条记录复制一遍 | 多抽率上升（字段 F1 不受影响，按设计） |
| 每篇丢掉一半记录 | 记录匹配率下降 |
| 只保留 1 篇预测 | 记录匹配率 < 50% |

**失败信号**：`selftest` 不到 100% → 评测代码有 bug，此时 `report.md` 里的任何数字都不能用。

### 4. 评测报表（`eval/run_eval.py`）

```bash
uv run python -m eval.run_eval --tag baseline
```

**通过标准**：`eval/report.md` 出现 5 节（总览 / 字段级 / 逐篇 / 分层 / 混淆样例），
头部写了 schema 版本、golden 与 predictions 的 sha256、运行命令与时间。

**怎么读**：

- 先看「记录匹配率」——它低说明记录切分粒度与 gold 不一致（例如把多行表当成一个样品）
- 再看「覆盖率」列——比表面积 gold 有值率只有约 42%（在已对齐记录里），
  不报覆盖率会把「没抽出来」误读成「抽错了」
- 口径 A（值对齐）是主口径，口径 B（顺序对齐）作对照；两者差得大说明记录切分有问题
- 表格行召回、含表分层要等解析线交付 `parse_report.json` 后才会启用

**复现要求**：同一条命令连跑两次，`report.md` 字节一致（sha256 相同）。

### 5. 批注字段扩展（后端 + 面板）

**后端**（不用起服务，用 TestClient 即可）：

```bash
uv run python -c "
from fastapi.testclient import TestClient
from backend.main import app
c = TestClient(app)
print(c.post('/api/runs/<run_id>/annotations', json={'record_index':0,'field':'比表面积','note':'x','corrected_value':'274.0 m2/g','reason':'多抽'}).json())
"
```

**通过标准**：POST 返回 201 且回显 `corrected_value` / `reason`；
`data/annotations/<run_id>.json` 里能看到这两个字段；GET 列表能取回；DELETE 返回 204。

**前端**：`npm run dev` → 悬停某条记录的某个字段 → 浮层里出现「修正值」「原因」两个输入框 →
填入并保存 → 该 run 的批注列表里能看到，`data/annotations/<run_id>.json` 同步落盘。
旧批注文件仍能正常读取（只增字段，不删不改）。

**失败信号**：填了修正值但 JSON 里没有 → 前端没把值传上去（检查 `ResultsTable` 的 save payload）。

## 产物清单

| 文件 | 说明 | 是否入库 |
| --- | --- | --- |
| `eval/data/golden.jsonl` | 264 条 gold，评测基准 | 入库（体积小、可复现） |
| `eval/data/predictions.jsonl` | 从 run 导出的预测 | 不入库 |
| `eval/report.md` | 每次评测的报表，覆盖写 | 不入库 |
| `eval/DESIGN.md` / `eval/schema.yaml` | 口径，改动要升版本 | 入库 |

## 第一周的已知边界

- 只有 3 篇论文有 run，所以 baseline 是 12 条对齐记录上的结论，方差大；20 篇子集要等解析线
- `report.md` 里 `prompt_version` / `model` 还是 `None`，因为 run 尚未记录（任务九补）
- 表格行召回、含表分层、文献类型分层都还没启用，依赖解析线产物与 20 篇人工打标
