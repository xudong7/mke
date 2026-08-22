/* App.tsx — 三区布局（左/中/右均可折叠）：左=论文列表+运行历史，中=PDF 查看器，右=流程看板+批注 */
import { ChevronLeft, ChevronsLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { HealthInfo, Paper, RunSummary } from "./types";
import { errText, fetchHealth, fetchPaperText, fetchPapers, fetchRun, fetchRuns } from "./api/client";
import { usePipeline } from "./hooks/usePipeline";
import { useAnnotations } from "./hooks/useAnnotations";
import { PaperBrowser } from "./components/paper/PaperBrowser";
import { PaperViewer } from "./components/paper/PaperViewer";
import { PipelineKanban } from "./components/pipeline/PipelineKanban";

export default function App() {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [papersLoading, setPapersLoading] = useState(true);
  const [selected, setSelected] = useState<Paper | null>(null);
  const [text, setText] = useState<string>("");
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [leftOpen, setLeftOpen] = useState(true);
  /** 聚焦模式：折叠左栏 + 加宽右栏（右栏始终常驻） */
  const [wideMode, setWideMode] = useState(false);
  /** 批注列表点击 → 滚动到对应记录 */
  const [recordJump, setRecordJump] = useState<{ index: number; token: number } | null>(null);

  const pipeline = usePipeline({
    paperId: selected?.id ?? null,
    text,
    hasPdf: selected?.has_pdf ?? false,
  });
  const annotationsApi = useAnnotations(pipeline.runId);

  /* 初始化：健康检查 + 论文列表 */
  useEffect(() => {
    void fetchHealth().then(setHealth).catch(() => setHealth(null));
    void fetchPapers()
      .then(setPapers)
      .catch(() => setPapers([]))
      .finally(() => setPapersLoading(false));
  }, []);

  const selectPaper = useCallback(
    async (paper: Paper) => {
      setSelected(paper);
      setText("");
      setRuns([]);
      pipeline.reset();
      try {
        setText(await fetchPaperText(paper.id));
      } catch (e) {
        alert(`加载论文文本失败：${errText(e)}`);
      }
    },
    [pipeline],
  );

  /* 刷新运行历史：论文切换 或 当前 run 状态变化（创建/完成/失败）时 */
  const refreshRuns = useCallback(async () => {
    if (!selected) return;
    try {
      setRuns(await fetchRuns(selected.id));
    } catch {
      /* 静默 */
    }
  }, [selected]);

  useEffect(() => {
    void refreshRuns();
  }, [refreshRuns, pipeline.runId, pipeline.runStatus]);

  const handleUploaded = useCallback(() => {
    void fetchPapers().then(setPapers);
  }, []);

  /** 历史 → 查看：完整恢复看板状态（零 LLM） */
  const handleLoadRun = useCallback(
    async (runId: string) => {
      try {
        const run = await fetchRun(runId);
        // 若 run 属于其他论文，先切换
        if (run.paper_id !== selected?.id) {
          const runPaper = papers.find((p) => p.id === run.paper_id);
          if (runPaper) {
            setSelected(runPaper);
            setText(await fetchPaperText(runPaper.id));
          }
        }
        pipeline.loadRun(run);
      } catch (e) {
        alert(`加载运行记录失败：${errText(e)}`);
      }
    },
    [pipeline, papers, selected?.id],
  );

  /** 历史 → 重新运行：新开一次 run，全量执行 */
  const handleRerunRun = useCallback(() => {
    if (pipeline.runStatus === "running") return;
    void pipeline.runAll({ fresh: true });
  }, [pipeline]);

  const handleSaveAnnotation = useCallback(
    async (
      target: { record_index: number; field?: string | null; value_snapshot?: string | null },
      note: string,
    ) => {
      await annotationsApi.add({ ...target, note });
    },
    [annotationsApi],
  );

  const handleJumpToRecord = useCallback((index: number) => {
    setRecordJump({ index, token: Date.now() });
  }, []);

  const uploadPapers = useMemo(() => papers.filter((p) => p.source === "upload"), [papers]);

  /** 聚焦模式切换：进入 → 折叠左栏+加宽右栏；退出 → 还原 */
  const toggleWide = () => {
    const next = !wideMode;
    setWideMode(next);
    setLeftOpen(!next);
  };

  return (
    <div className="app">
      <main className={`app-main${wideMode ? " wide" : ""}`}>
        {leftOpen ? (
          <>
            <aside className="sidebar-left">
              <PaperBrowser
                papers={uploadPapers}
                selected={selected}
                runs={runs}
                currentRunId={pipeline.runId}
                busy={pipeline.runStatus === "running"}
                onSelectPaper={(p) => void selectPaper(p)}
                onUploaded={handleUploaded}
                onLoadRun={(rid) => void handleLoadRun(rid)}
                onRerunRun={handleRerunRun}
              />
              <div
                className="panel-handle panel-handle-left"
                onClick={() => setLeftOpen(false)}
                title="折叠论文库"
                role="button"
                aria-label="折叠论文库"
              >
                <ChevronLeft size={13} />
              </div>
            </aside>
          </>
        ) : (
          <div
            className="sidebar-rail"
            onClick={() => setLeftOpen(true)}
            title="展开论文库"
            role="button"
            aria-label="展开论文库"
          >
            <ChevronRight size={14} />
          </div>
        )}

        <section className="pane-center">
          <PaperViewer paper={selected} text={text} />
          {papersLoading && <div className="viewer-loading">正在加载论文库…</div>}
        </section>

        <div className="sidebar-right-wrap">
          <aside className="sidebar-right">
            <PipelineKanban
              steps={pipeline.steps}
              records={pipeline.records}
              runId={pipeline.runId}
              runStatus={pipeline.runStatus}
              llmConfigured={health?.llm_configured ?? false}
              llmModel={health?.model ?? null}
              isStepReady={pipeline.isStepReady}
              onRunStep={(id) => void pipeline.runStep(id)}
              onRunAll={() => void pipeline.runAll()}
              onReset={pipeline.reset}
              annotations={annotationsApi.annotations}
              onSaveAnnotation={handleSaveAnnotation}
              onDeleteAnnotation={(id) => annotationsApi.remove(id)}
              onJumpToRecord={handleJumpToRecord}
              recordJump={recordJump}
            />
          </aside>
          <div
            className="panel-handle panel-handle-right"
            onClick={toggleWide}
            title="聚焦模式：折叠左栏、加宽结果面板"
            role="button"
            aria-label="聚焦模式：折叠左栏、加宽结果面板"
          >
            <ChevronsLeft size={13} />
          </div>
        </div>
      </main>
    </div>
  );
}
