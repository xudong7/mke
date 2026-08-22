/* PaperBrowser.tsx — 左侧栏：论文列表 + 上传 + 历史解析结果 */
import type { Paper, RunSummary } from "../../types";
import { PaperList } from "./PaperList";
import { RunHistory } from "./RunHistory";

interface Props {
  papers: Paper[];
  selected: Paper | null;
  runs: RunSummary[];
  currentRunId: string | null;
  busy: boolean;
  onSelectPaper: (p: Paper) => void;
  onUploaded: () => void;
  onCollapse: () => void;
  onLoadRun: (runId: string) => void;
  onRerunRun: () => void;
}

export function PaperBrowser({
  papers,
  selected,
  runs,
  currentRunId,
  busy,
  onSelectPaper,
  onUploaded,
  onCollapse,
  onLoadRun,
  onRerunRun,
}: Props) {
  return (
    <div className="paper-browser">
      <PaperList
        papers={papers}
        selectedId={selected?.id ?? null}
        onSelect={onSelectPaper}
        onUploaded={onUploaded}
        onCollapse={onCollapse}
      />
      <RunHistory
        runs={runs}
        currentRunId={currentRunId}
        busy={busy}
        onLoad={onLoadRun}
        onRerun={onRerunRun}
      />
    </div>
  );
}
