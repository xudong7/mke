/* PipelineKanban.tsx — 流程看板容器：时间轴 + 结果表 + 批注桥接 */
import { useMemo } from "react";
import type { Annotation, ExtractRecord, PipelineStep, RunStatus, StepId } from "../../types";
import { PipelineTimeline } from "./PipelineTimeline";
import { ResultsTable } from "./ResultsTable";
import { LLMCostBanner } from "./LLMCostBanner";

interface Props {
  steps: PipelineStep[];
  records: ExtractRecord[];
  paperLabel: string;
  runId: string | null;
  runStatus: RunStatus | null;
  llmConfigured: boolean;
  isStepReady: (id: StepId) => boolean;
  onRunStep: (id: StepId) => void;
  onRunAll: () => void;
  onReset: () => void;
  /* 结果批注（v2） */
  annotations: Annotation[];
  onSaveAnnotation: (
    target: { record_index: number; field?: string | null; value_snapshot?: string | null },
    note: string,
  ) => Promise<void>;
  recordJump: { index: number; token: number } | null;
}

export function PipelineKanban({
  steps,
  records,
  paperLabel,
  runId,
  runStatus,
  llmConfigured,
  isStepReady,
  onRunStep,
  onRunAll,
  onReset,
  annotations,
  onSaveAnnotation,
  recordJump,
}: Props) {
  const anyRunning = runStatus === "running";
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
        <div className="kanban-title" title={paperLabel}>
          {paperLabel || "未选择论文"}
        </div>
        <div className="kanban-actions">
          {runId && (
            <span className={`run-badge mono status-${runStatus ?? "pending"}`}>
              run {runId.slice(0, 8)} · {runStatus}
            </span>
          )}
          <button className="btn" onClick={onReset} disabled={!anyDone}>
            重置
          </button>
          <button className="btn btn-primary" onClick={onRunAll} disabled={anyRunning}>
            全部运行
          </button>
        </div>
      </div>

      <LLMCostBanner llmConfigured={llmConfigured} structurizeEstimate={structurizeEstimate} />

      <PipelineTimeline steps={steps} isStepReady={isStepReady} onRunStep={onRunStep} />

      <ResultsTable
        records={records}
        annotations={annotations}
        onSaveAnnotation={onSaveAnnotation}
        recordJump={recordJump}
      />
    </div>
  );
}
