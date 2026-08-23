/* RunHistory.tsx — 选中论文的历史运行记录（点击条目查看） */
import type { RunSummary } from "../../types";

interface Props {
  runs: RunSummary[];
  currentRunId: string | null;
  busy: boolean;
  onLoadRun: (runId: string) => void;
}

export function RunHistory({ runs, currentRunId, busy, onLoadRun }: Props) {
  return (
    <div className="run-history">
      {runs.length === 0 && (
        <div className="run-history-empty">暂无运行记录。运行流水线后自动保存。</div>
      )}
      {runs.map((r) => (
        <button
          key={r.id}
          className={`run-history-item${r.id === currentRunId ? " current" : ""}`}
          onClick={() => onLoadRun(r.id)}
          disabled={busy}
          title="点击查看该次运行记录"
        >
          <div className="run-history-item-head">
            <span className={`dot status-${r.status}`} />
            <span className="run-history-time mono">
              {new Date(r.created_at).toLocaleString()}
            </span>
            <span className="run-history-count mono text-2">{r.record_count} 条</span>
          </div>
        </button>
      ))}
    </div>
  );
}
