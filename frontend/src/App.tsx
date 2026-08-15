/* App.tsx — 左右分栏双面板：左=PDF 论文浏览器，右=解析流程看板 + 批注交互 */
import { useCallback, useEffect, useMemo, useState } from "react";
import type { HealthInfo, Paper, PendingSelection } from "./types";
import { errText, fetchHealth, fetchPapers, fetchPaperText } from "./api/client";
import { usePipeline } from "./hooks/usePipeline";
import { useAnnotations } from "./hooks/useAnnotations";
import { PaperBrowser } from "./components/paper/PaperBrowser";
import { PipelineKanban } from "./components/pipeline/PipelineKanban";
import { AnnotationPanel } from "./components/annotation/AnnotationPanel";

export default function App() {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [papersLoading, setPapersLoading] = useState(true);
  const [selected, setSelected] = useState<Paper | null>(null);
  const [text, setText] = useState<string>("");
  const [selection, setSelection] = useState<PendingSelection | null>(null);
  const [jumpRequest, setJumpRequest] = useState<{ page: number; token: number } | null>(null);

  const annotationsApi = useAnnotations(selected?.id ?? null);

  const pipeline = usePipeline({
    paperId: selected?.id ?? null,
    text,
    hasPdf: selected?.has_pdf ?? false,
  });

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
      setSelection(null);
      setText("");
      pipeline.reset();
      try {
        setText(await fetchPaperText(paper.id));
      } catch (e) {
        alert(`加载论文文本失败：${errText(e)}`);
      }
    },
    [pipeline],
  );

  const handleUploaded = useCallback(() => {
    void fetchPapers().then(setPapers);
  }, []);

  const handleSelectText = useCallback((sel: PendingSelection) => {
    setSelection(sel);
  }, []);

  const handleSaveAnnotation = useCallback(
    async (note: string) => {
      if (!selected || !selection) return;
      await annotationsApi.add({
        page: selection.page,
        quote: selection.quote,
        note,
        anchor: {
          rects: selection.rects,
          page_width: 0,
          page_height: 0,
        },
      });
      setSelection(null);
    },
    [selected, selection, annotationsApi],
  );

  const handleJump = useCallback((page: number) => {
    setJumpRequest({ page, token: Date.now() });
  }, []);

  const paperLabel = useMemo(() => {
    if (!selected) return "";
    return selected.title || selected.id;
  }, [selected]);

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-logo">MKE</div>
        <div className="app-title">介孔材料文献知识自动抽取系统</div>
        <div className="app-header-right mono">
          {health && (
            <>
              <span className="text-2">模型 {health.model}</span>
              <span className={`llm-badge ${health.llm_configured ? "ok" : "missing"}`}>
                {health.llm_configured ? "LLM 已配置" : "未配置 API Key"}
              </span>
            </>
          )}
        </div>
      </header>

      <main className="app-main">
        <section className="pane-left">
          <PaperBrowser
            papers={papers}
            selected={selected}
            text={text}
            annotations={annotationsApi.annotations}
            onSelectPaper={(p) => void selectPaper(p)}
            onUploaded={handleUploaded}
            onSelectText={handleSelectText}
            onJumpRequest={jumpRequest}
          />
          {papersLoading && <div className="viewer-loading">正在加载论文库…</div>}
        </section>

        <section className="pane-right">
          <PipelineKanban
            steps={pipeline.steps}
            records={pipeline.records}
            paperLabel={paperLabel}
            llmConfigured={health?.llm_configured ?? false}
            isStepReady={pipeline.isStepReady}
            onRunStep={(id) => void pipeline.runStep(id)}
            onRunAll={() => void pipeline.runAll()}
            onReset={pipeline.reset}
          />
          <AnnotationPanel
            selection={selection}
            annotations={annotationsApi.annotations}
            onSave={handleSaveAnnotation}
            onCancel={() => setSelection(null)}
            onDelete={(id) => annotationsApi.remove(id)}
            onJump={handleJump}
          />
        </section>
      </main>
    </div>
  );
}
