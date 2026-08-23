/* PipelineKanban.tsx — 流程看板：时间轴/结果表 + 批注 tab（看板 | 批注(n)） */
import { Cpu, LayoutDashboard, MessageSquare, Play, RotateCcw } from "lucide-react";
import { useState } from "react";
import type { Annotation, ExtractRecord, PipelineStep, RunStatus, StepId } from "../../types";
import { PipelineTimeline } from "./PipelineTimeline";
import { ResultsTable } from "./ResultsTable";
import { AnnotationPanel } from "../annotation/AnnotationPanel";

interface Props {
  steps: PipelineStep[];
  records: ExtractRecord[];
  runStatus: RunStatus | null;
  llmConfigured: boolean;
  llmModel: string | null;
  isStepReady: (id: StepId) => boolean;
  onRunStep: (id: StepId) => void;
  onRunAll: () => void;
  onReset: () => void;
  /* 结果批注（v2/v3） */
  annotations: Annotation[];
  onSaveAnnotation: (
    target: { record_index: number; field?: string | null; value_snapshot?: string | null },
    note: string,
  ) => Promise<void>;
  onDeleteAnnotation: (id: string) => Promise<void>;
  onJumpToRecord: (index: number) => void;
  recordJump: { index: number; token: number } | null;
}

export function PipelineKanban({
  steps,
  records,
  runStatus,
  llmConfigured,
  llmModel,
  isStepReady,
  onRunStep,
  onRunAll,
  onReset,
  annotations,
  onSaveAnnotation,
  onDeleteAnnotation,
  onJumpToRecord,
  recordJump,
}: Props) {
  const [tab, setTab] = useState<"board" | "annotations">("board");
  const anyRunning = runStatus === "running";
  const anyDone = steps.some((s) => s.status === "done");

  return (
    <div className="kanban">
      <div className="kanban-header">
        <div className="kanban-tabs">
          <button
            className={`kanban-tab${tab === "board" ? " active" : ""}`}
            onClick={() => setTab("board")}
          >
            <LayoutDashboard size={14} />
            看板
          </button>
          <button
            className={`kanban-tab${tab === "annotations" ? " active" : ""}`}
            onClick={() => setTab("annotations")}
          >
            <MessageSquare size={14} />
            批注
            <span className={`count${annotations.length > 0 ? " has" : ""}`}>
              ({annotations.length})
            </span>
          </button>
        </div>
        <div className="kanban-actions">
          <span
            className={`kanban-llm ${llmConfigured ? "ok" : "missing"}`}
            title={llmConfigured ? `LLM 已配置 · 模型 ${llmModel ?? "未知"}` : "未配置 OPENAI_API_KEY，LLM 步骤不可用"}
          >
            <Cpu size={14} />
          </span>
          <button className="btn btn-icon" onClick={onReset} disabled={!anyDone} aria-label="重置" title="重置全部步骤状态">
            <RotateCcw size={14} />
          </button>
          <button className="btn btn-primary" onClick={onRunAll} disabled={anyRunning}>
            <Play size={14} />
            全部运行
          </button>
        </div>
      </div>

      {tab === "board" ? (
        <div className="kanban-board">
          <PipelineTimeline steps={steps} isStepReady={isStepReady} onRunStep={onRunStep} />
          <ResultsTable
            records={records}
            annotations={annotations}
            onSaveAnnotation={onSaveAnnotation}
            recordJump={recordJump}
          />
        </div>
      ) : (
        <AnnotationPanel
          annotations={annotations}
          onDelete={onDeleteAnnotation}
          onJumpToRecord={(i) => {
            setTab("board"); // 切回看板，让滚动闪烁可见
            onJumpToRecord(i);
          }}
        />
      )}
    </div>
  );
}
