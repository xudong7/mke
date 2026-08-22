/* RunHistory.tsx — 选中论文的历史运行记录（查看 / 重新运行） */
import { Eye, RotateCcw } from "lucide-react";
import type { RunSummary } from "../../types";

interface Props {
  runs: RunSummary[];
  currentRunId: string | null;
  busy: boolean;
  onLoad: (runId: string) => void;
  onRerun: () => void;
}

const STEP_LABELS: Record<string, string> = {
  parse: "解析",
  route: "路由",
  extract: "抽取",
  cite: "引用",
  structurize: "结构化",
};

export function RunHistory({ runs, currentRunId, busy, onLoad, onRerun }: Props) {
  const doneCount = (r: RunSummary) =>
    Object.values(r.step_statuses).filter((s) => s === "done").length;

  return (
    <div className="run-history">
      <div className="run-history-header">
        <span>历史解析结果</span>
        <span className="mono text-2">{runs.length} 次</span>
      </div>
      {runs.length === 0 && (
        <div className="run-history-empty">暂无运行记录。运行流水线后自动保存。</div>
      )}
      {runs.map((r) => (
        <div
          key={r.id}
          className={`run-history-item${r.id === currentRunId ? " current" : ""}`}
        >
          <div className="run-history-item-head">
            <span className={`dot status-${r.status}`} />
            <span className="run-history-time mono">
              {new Date(r.created_at).toLocaleString()}
            </span>
            <span className="run-history-count mono text-2">{r.record_count} 条</span>
            <span className="run-history-steps" title={`${doneCount(r)}/5 步骤完成`}>
              {Object.entries(r.step_statuses).map(([step, status]) => (
                <span
                  key={step}
                  className={`step-dot status-${status}`}
                  title={`${STEP_LABELS[step] ?? step} · ${status}`}
                />
              ))}
            </span>
            <span className="run-history-count mono text-2">{doneCount(r)}/5</span>
            <div className="run-history-actions">
              <button
                className="btn btn-icon"
                onClick={() => onLoad(r.id)}
                disabled={busy}
                aria-label="查看"
                title="查看该次运行记录"
              >
                <Eye size={14} />
              </button>
              <button
                className="btn btn-icon"
                onClick={onRerun}
                disabled={busy || r.status === "running"}
                aria-label="重新运行"
                title="以该论文重新运行完整流水线（新开一次运行记录）"
              >
                <RotateCcw size={14} />
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
