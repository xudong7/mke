/* PipelineKanban.tsx — 5 步解析流程看板 */
import { useMemo } from "react";
import type { ExtractRecord, PipelineStep, StepId } from "../../types";
import { StepCard } from "./StepCard";
import { ResultsTable } from "./ResultsTable";
import { LLMCostBanner } from "./LLMCostBanner";

interface Props {
  steps: PipelineStep[];
  records: ExtractRecord[];
  paperLabel: string;
  llmConfigured: boolean;
  /** 步骤是否可以执行（依赖就绪） */
  isStepReady: (id: StepId) => boolean;
  onRunStep: (id: StepId) => void;
  onRunAll: () => void;
  onReset: () => void;
}

export function PipelineKanban({
  steps,
  records,
  paperLabel,
  llmConfigured,
  isStepReady,
  onRunStep,
  onRunAll,
  onReset,
}: Props) {
  const anyRunning = steps.some((s) => s.status === "running");
  const anyDone = steps.some((s) => s.status === "done");

  // 步骤⑤ 时长预估：按记录数提示（逐条 LLM 调用）
  const structurizeEstimate = useMemo(() => {
    const n = records.length;
    if (n === 0) return null;
    return `共 ${n} 条记录，逐条结构化预计 ${Math.round(n * 30)}–${Math.round(n * 60)} 秒`;
  }, [records.length]);

  return (
    <div className="kanban">
      <div className="kanban-header">
        <div className="kanban-title">{paperLabel || "未选择论文"}</div>
        <div className="kanban-actions">
          <button className="btn" onClick={onReset} disabled={!anyDone}>
            重置
          </button>
          <button className="btn btn-primary" onClick={onRunAll} disabled={anyRunning}>
            全部运行
          </button>
        </div>
      </div>

      <LLMCostBanner llmConfigured={llmConfigured} structurizeEstimate={structurizeEstimate} />

      <div className="kanban-steps">
        {steps.map((s) => (
          <StepCard key={s.id} step={s} ready={isStepReady(s.id)} onRun={() => onRunStep(s.id)} />
        ))}
      </div>

      {records.length > 0 && <ResultsTable records={records} />}
    </div>
  );
}
