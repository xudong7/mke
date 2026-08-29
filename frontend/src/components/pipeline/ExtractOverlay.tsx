/* ExtractOverlay.tsx — 提取过程可视化（移植 mke-main index_enhanced 的双层加载动画 + 步骤进度列表）
 * 覆盖在流程面板上：双层旋转加载器 + 标题/副标题 + 按流水线真实状态推进的 progress-steps
 *（版面解析 → 文献分类 → 知识抽取 → 引用标注 → 结构化处理，随步骤 done/active 高亮）。
 */
import type { PipelineStep, StepId } from "../../types";

interface VisStep {
  id: StepId;
  title: string;
  desc: string;
}

/** 可视化步骤（按 mke 真实流水线顺序；短语/说明对齐 mke-main index_enhanced） */
const VIS_STEPS: VisStep[] = [
  { id: "parse", title: "版面解析", desc: "PDF 版面重建（本地计算）" },
  { id: "route", title: "文献分类", desc: "识别文献类型，推荐抽取策略" },
  { id: "extract", title: "知识抽取", desc: "提取合成条件、表征数据等" },
  { id: "cite", title: "引用标注", desc: "标注来源文本与推理说明" },
  { id: "structurize", title: "结构化处理", desc: "数值拆分与格式规范化" },
];

/** 运行中步骤的副标题 */
const STEP_SUB: Record<StepId, string> = {
  parse: "版面重建中…",
  route: "正在识别文献类型…",
  extract: "正在提取关键信息…",
  cite: "正在标注引用来源…",
  structurize: "正在进行数值结构化…",
};

interface Props {
  visible: boolean;
  steps: PipelineStep[];
}

function stepStatus(st: PipelineStep | undefined): "done" | "active" | "pending" {
  if (!st) return "pending";
  if (st.skipped) return "done";
  if (st.status === "done") return "done";
  if (st.status === "running") return "active";
  return "pending";
}

export function ExtractOverlay({ visible, steps }: Props) {
  if (!visible) return null;
  const running = steps.find((s) => s.status === "running");
  const sub = (running && STEP_SUB[running.id]) || "准备中…";

  return (
    <div className="extract-overlay" aria-live="polite">
      <div className="loader">
        <div className="loader-ring" />
        <div className="loader-ring" />
      </div>
      <div className="loading-title">正在分析文献</div>
      <div className="loading-subtitle">{sub}</div>

      <div className="progress-steps">
        {VIS_STEPS.map((vs, i) => {
          const status = stepStatus(steps.find((s) => s.id === vs.id));
          return (
            <div key={vs.id} className={`progress-step ${status}`}>
              <div className="step-indicator">{status === "done" ? "✓" : i + 1}</div>
              <div className="step-content">
                <div className="step-title">{vs.title}</div>
                <div className="step-desc">{vs.desc}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}