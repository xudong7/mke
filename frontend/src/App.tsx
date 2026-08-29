/* App.tsx — 三区布局（左/中/右均可折叠）：左=论文列表+运行历史，中=PDF 查看器，右=流程看板+批注 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FieldHighlight, HealthInfo, Paper, RunSummary } from "./types";
import {
  errText,
  exportExcel,
  exportRunExcel,
  fetchHealth,
  fetchPaperText,
  fetchPapers,
  fetchRun,
  fetchRuns,
} from "./api/client";
import { usePipeline } from "./hooks/usePipeline";
import { useAnnotations } from "./hooks/useAnnotations";
import { PaperBrowser } from "./components/paper/PaperBrowser";
import { PaperViewer, type PaperViewerHandle } from "./components/paper/PaperViewer";
import { PipelineKanban } from "./components/pipeline/PipelineKanban";

/** 提取动画覆盖的基础字段（与 citation_agent 重点关注字段一致） */
const EXTRACT_FIELDS = [
  "组装方式",
  "溶剂体系",
  "pH值_酸碱浓度",
  "表面活性剂种类",
  "表面活性剂浓度",
  "硅/钛源种类_浓度",
  "盐种类_浓度",
  "合成温度",
  "介孔结构",
  "比表面积",
  "孔径",
  "产物形态",
  "其他变量",
];

export default function App() {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [papersLoading, setPapersLoading] = useState(true);
  const [selected, setSelected] = useState<Paper | null>(null);
  const [text, setText] = useState<string>("");
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [leftOpen, setLeftOpen] = useState(true);
  const [centerOpen, setCenterOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  /** 批注列表点击 → 滚动到对应记录 */
  const [recordJump, setRecordJump] = useState<{ index: number; token: number } | null>(null);
  /** 原文定位中枢（中间面板） */
  const viewerRef = useRef<PaperViewerHandle>(null);

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

  /** 导出当前运行结果到 Excel */
  const handleExport = useCallback(() => {
    void exportExcel(pipeline.records, selected?.id).catch((e) =>
      alert(`导出失败：${errText(e)}`),
    );
  }, [pipeline.records, selected?.id]);

  /** 导出历史 run 到 Excel */
  const handleExportRun = useCallback((runId: string) => {
    void exportRunExcel(runId).catch((e) => alert(`导出失败：${errText(e)}`));
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

  /** 原文定位：结果表引用句 → 中间面板高亮 + 滚动 */
  const handleLocate = useCallback((field: string, citations: string[]) => {
    void viewerRef.current?.locate(citations, field);
  }, []);

  /** 提取过程动画：步骤 running→done 时，驱动中间面板对原文依据做标注框选 */
  const prevStepsRef = useRef<Record<string, string>>({});
  useEffect(() => {
    const cur: Record<string, string> = {};
    pipeline.steps.forEach((s) => {
      cur[s.id] = s.status;
    });
    const prev = prevStepsRef.current;
    // 仅在真实执行（running→done）时触发，历史加载/跳过（pending→done）不触发
    const justDone = (id: string) => cur[id] === "done" && prev[id] === "running";

    if (justDone("extract")) {
      const fields: FieldHighlight[] = [];
      for (const r of pipeline.records) {
        for (const f of EXTRACT_FIELDS) {
          const v = r[f];
          if (!v) continue;
          fields.push({
            field: f,
            sentences: (r["字段引用"]?.[f] as string[] | undefined) ?? [],
            value: String(v),
          });
        }
      }
      if (fields.length) void viewerRef.current?.animateFields(fields);
    }

    if (justDone("cite")) {
      const fields: FieldHighlight[] = [];
      for (const r of pipeline.records) {
        for (const [field, sentences] of Object.entries(r["字段引用"] ?? {})) {
          if (!Array.isArray(sentences) || sentences.length === 0) continue;
          fields.push({
            field,
            sentences: sentences as string[],
            value: String(r[field] ?? ""),
          });
        }
      }
      if (fields.length) void viewerRef.current?.animateFields(fields);
    }

    prevStepsRef.current = cur;
  }, [pipeline.steps, pipeline.records]);

  const uploadPapers = useMemo(() => papers.filter((p) => p.source === "upload"), [papers]);
  const paperLabel = selected?.title || selected?.id || "";

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

      <main className={`app-main${centerOpen ? "" : " center-collapsed"}`}>
        {leftOpen ? (
          <>
            <div
              className="edge-strip edge-strip-left"
              onClick={() => setLeftOpen(false)}
              title="折叠论文库"
              role="button"
            >
              <span className="edge-strip-grip" />
            </div>
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
                onExportRun={handleExportRun}
              />
            </aside>
          </>
        ) : (
          <div className="sidebar-rail" onClick={() => setLeftOpen(true)} title="展开论文库">
            ›
          </div>
        )}

        {centerOpen && (
          <section className="pane-center">
            <PaperViewer ref={viewerRef} paper={selected} text={text} />
            {papersLoading && <div className="viewer-loading">正在加载论文库…</div>}
          </section>
        )}
        <div
          className={centerOpen ? "edge-strip edge-strip-center" : "sidebar-rail rail-center"}
          onClick={() => setCenterOpen((v) => !v)}
          title={centerOpen ? "折叠论文预览" : "展开论文预览"}
          role="button"
        >
          {centerOpen ? <span className="edge-strip-grip" /> : "‹"}
        </div>

        {rightOpen ? (
          <>
            <aside className="sidebar-right">
              <PipelineKanban
                steps={pipeline.steps}
                records={pipeline.records}
                paperLabel={paperLabel}
                runId={pipeline.runId}
                runStatus={pipeline.runStatus}
                llmConfigured={health?.llm_configured ?? false}
                isStepReady={pipeline.isStepReady}
                onRunStep={(id) => void pipeline.runStep(id)}
                onRunAll={() => void pipeline.runAll()}
                onReset={pipeline.reset}
                onExport={handleExport}
                annotations={annotationsApi.annotations}
                onSaveAnnotation={handleSaveAnnotation}
                onDeleteAnnotation={(id) => annotationsApi.remove(id)}
                onJumpToRecord={handleJumpToRecord}
                recordJump={recordJump}
                onLocate={handleLocate}
              />
            </aside>
            <div
              className="edge-strip edge-strip-right"
              onClick={() => setRightOpen(false)}
              title="折叠流程看板"
              role="button"
            >
              <span className="edge-strip-grip" />
            </div>
          </>
        ) : (
          <div className="sidebar-rail rail-right" onClick={() => setRightOpen(true)} title="展开流程看板">
            ‹
          </div>
        )}
      </main>
    </div>
  );
}
