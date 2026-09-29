/* PipelineTimeline.tsx — 横向时间轴：5 步节点 + 连接线 + 步骤详情 */
import { useState } from "react";
import type { PipelineStep, StepId } from "../../types";
import { StepDetail } from "./StepDetail";

interface Props {
  steps: PipelineStep[];
  isStepReady: (id: StepId) => boolean;
  onRunStep: (id: StepId) => void;
}

export function PipelineTimeline({ steps, isStepReady, onRunStep }: Props) {
  const [selectedId, setSelectedId] = useState<StepId>("route");
  const selected = steps.find((s) => s.id === selectedId) ?? steps[0];

  return (
    <div className="timeline">
      <div className="timeline-track">
        {steps.map((s, i) => {
          const ready = isStepReady(s.id);
          return (
            <div key={s.id} className="timeline-segment">
              <button
                className={`timeline-node status-${s.status}${selectedId === s.id ? " active" : ""}`}
                onClick={() => setSelectedId(s.id)}
                title={s.description}
              >
                <span className="dot" />
                <span className="timeline-label">{s.label.replace(/^[①-⑤]\s*/, "")}</span>
                {s.took_ms !== undefined && (
                  <span className="timeline-duration mono">{(s.took_ms / 1000).toFixed(1)}s</span>
                )}
                {!ready && s.status === "pending" && (
                  <span className="timeline-lock mono">待前序</span>
                )}
              </button>
              {i < steps.length - 1 && (
                <div className={`timeline-connector ${s.status === "done" ? "done" : ""}`} />
              )}
            </div>
          );
        })}
      </div>

      {selected && (
        <div className={`timeline-detail status-${selected.status}`}>
          <div className="timeline-detail-head">
            <span className="dot" />
            <span className="timeline-detail-title">{selected.label}</span>
            <span className="timeline-detail-desc">{selected.description}</span>
            <div className="timeline-detail-actions">
              {selected.took_ms !== undefined && (
                <span className="mono text-2">{(selected.took_ms / 1000).toFixed(1)}s</span>
              )}
              {selected.status === "done" && !selected.skipped && (
                <button className="btn btn-sm" onClick={() => onRunStep(selected.id)}>
                  重跑
                </button>
              )}
              {selected.status === "error" && (
                <button className="btn btn-sm" onClick={() => onRunStep(selected.id)}>
                  重试
                </button>
              )}
              {(selected.status === "pending" || selected.status === "running") && (
                <button
                  className="btn btn-sm btn-primary"
                  onClick={() => onRunStep(selected.id)}
                  disabled={!isStepReady(selected.id) || selected.status === "running"}
                >
                  {selected.status === "running" ? "处理中…" : "运行"}
                </button>
              )}
            </div>
          </div>
          {selected.skipped && (
            <div className="step-skipped">
              {(selected.payload as { reason?: string } | undefined)?.reason ?? "已跳过"}
            </div>
          )}
          {selected.status === "error" && <div className="step-error">{selected.error}</div>}
          {selected.warning && selected.status === "done" && (
            <div className="step-warning">{selected.warning}</div>
          )}
          {selected.payload !== undefined && <StepDetail step={selected} />}
        </div>
      )}
    </div>
  );
}
