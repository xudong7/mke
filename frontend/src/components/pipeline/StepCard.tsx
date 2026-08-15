/* StepCard.tsx — 单个流水线步骤卡片：状态信号色 + 可展开中间结果 */
import { useState } from "react";
import type { PipelineStep } from "../../types";

interface Props {
  step: PipelineStep;
  ready: boolean;
  onRun: () => void;
}

export function StepCard({ step, ready, onRun }: Props) {
  const [expanded, setExpanded] = useState(false);
  const canRun = ready && step.status !== "running";

  return (
    <div className={`step-card status-${step.status}`}>
      <div className="step-card-head">
        <span className="dot" />
        <div className="step-card-title">
          <div>{step.label}</div>
          <div className="step-card-desc">{step.description}</div>
        </div>
        <div className="step-card-actions">
          {step.took_ms !== undefined && (
            <span className="step-duration mono">{(step.took_ms / 1000).toFixed(1)}s</span>
          )}
          {step.status === "done" && !step.skipped && (
            <button className="btn btn-sm" onClick={onRun} disabled={!canRun}>
              重跑
            </button>
          )}
          {step.status === "error" && (
            <button className="btn btn-sm" onClick={onRun} disabled={!canRun}>
              重试
            </button>
          )}
          {step.status === "pending" && (
            <button className="btn btn-sm btn-primary" onClick={onRun} disabled={!canRun}>
              {step.id === "parse" ? "解析" : "运行"}
            </button>
          )}
          {step.status === "running" && <span className="step-running mono">处理中…</span>}
          {step.payload !== undefined && (
            <button className="btn btn-sm" onClick={() => setExpanded((e) => !e)}>
              {expanded ? "收起" : "详情"}
            </button>
          )}
        </div>
      </div>

      {step.skipped && (
        <div className="step-skipped">
          {(step.payload as { reason?: string } | undefined)?.reason ?? "已跳过"}
        </div>
      )}
      {step.status === "error" && <div className="step-error">{step.error}</div>}
      {step.warning && step.status === "done" && (
        <div className="step-warning">{step.warning}</div>
      )}

      {expanded && step.payload !== undefined && (
        <div className="step-payload mono">
          <pre>{JSON.stringify(step.payload, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
