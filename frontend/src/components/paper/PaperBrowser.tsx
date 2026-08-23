/* PaperBrowser.tsx — 左侧栏：tabs 导航（论文 | 历史）+ 上传 + 内容区 */
import { FileUp, History, Upload } from "lucide-react";
import { useRef, useState } from "react";
import type { Paper, RunSummary } from "../../types";
import { uploadPdf } from "../../api/client";
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
  onLoadRun: (runId: string) => void;
}

export function PaperBrowser({
  papers,
  selected,
  runs,
  currentRunId,
  busy,
  onSelectPaper,
  onUploaded,
  onLoadRun,
}: Props) {
  const [tab, setTab] = useState<"papers" | "runs">("papers");
  const fileRef = useRef<HTMLInputElement>(null);

  const handleUpload = async (file: File) => {
    try {
      await uploadPdf(file);
      onUploaded();
    } catch (e) {
      alert(`上传失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  return (
    <div className="paper-browser">
      <div className="kanban-header">
        <div className="kanban-tabs">
          <button
            className={`kanban-tab${tab === "papers" ? " active" : ""}`}
            onClick={() => setTab("papers")}
          >
            <FileUp size={14} />
            论文
          </button>
          <button
            className={`kanban-tab${tab === "runs" ? " active" : ""}`}
            onClick={() => setTab("runs")}
          >
            <History size={14} />
            历史
            <span className={`count${runs.length > 0 ? " has" : ""}`}>({runs.length})</span>
          </button>
        </div>
        <div className="kanban-actions">
          <button
            className="btn btn-icon"
            onClick={() => fileRef.current?.click()}
            aria-label="上传 PDF"
            title="上传 PDF"
          >
            <Upload size={14} />
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="application/pdf"
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleUpload(f);
              e.target.value = "";
            }}
          />
        </div>
      </div>

      {tab === "papers" ? (
        <PaperList papers={papers} selectedId={selected?.id ?? null} onSelect={onSelectPaper} />
      ) : (
        <RunHistory
          runs={runs}
          currentRunId={currentRunId}
          busy={busy}
          onLoadRun={onLoadRun}
        />
      )}
    </div>
  );
}
