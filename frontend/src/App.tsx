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

/* ---- 中栏分隔条：拖拽调节文献预览宽度（宽 → PDF 适应宽度后放大） ---- */
/** 右栏最小宽度（与 CSS .sidebar-right 的 min-width 一致） */
const RIGHT_MIN = 400;
/** 中栏（文献预览）最小宽度，防止拖到不可读 */
const CENTER_MIN = 360;

/** 右栏可用的最大宽度：三栏容器宽度 − 左栏与手柄 − 中栏最小值 */
function maxRightWidth(main: HTMLElement): number {
  const others = Array.from(main.children).filter(
    (el) =>
      !el.classList.contains("sidebar-right") && !el.classList.contains("pane-center"),
  );
  const othersW = others.reduce((sum, el) => sum + el.getBoundingClientRect().width, 0);
  return main.clientWidth - othersW - CENTER_MIN;
}

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
  /** 右栏宽度（px）：由中栏分隔条拖拽调节；null = 用 CSS 默认 520px */
  const [rightWidth, setRightWidth] = useState<number | null>(null);
  /** 批注列表点击 → 滚动到对应记录 */
  const [recordJump, setRecordJump] = useState<{ index: number; token: number } | null>(null);
  /** 原文定位中枢（中间面板） */
  const viewerRef = useRef<PaperViewerHandle>(null);
  /** 三栏容器（拖拽时量取可用宽度） */
  const mainRef = useRef<HTMLElement>(null);
  /** 中栏分隔条拖拽状态 */
  const dragRef = useRef<{ startX: number; startW: number; min: number; max: number } | null>(null);

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

  /* ---- 中栏分隔条拖拽：改变右栏宽度，中栏（flex:1）自动吃掉剩余空间 ---- */

  const beginDrag = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const main = mainRef.current;
    const right = main?.querySelector<HTMLElement>(".sidebar-right");
    if (!main || !right) return;
    const max = Math.max(RIGHT_MIN, maxRightWidth(main));
    dragRef.current = {
      startX: e.clientX,
      startW: right.getBoundingClientRect().width,
      min: Math.min(RIGHT_MIN, max),
      max,
    };
    // 指针捕获：拖出元素外仍持续收到事件
    e.currentTarget.setPointerCapture(e.pointerId);
    document.body.classList.add("col-resizing");
    // 拖动分隔条 = 要求 PDF 重新适配新宽度。
    // 点过 +/− 手动缩放会退出「适应宽度」模式，若不在此重置，
    // 拖动后 PDF 会保持旧缩放，中栏变窄时画面被截断。
    viewerRef.current?.refit();
    e.preventDefault();
  }, []);

  const moveDrag = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const d = dragRef.current;
    if (!d) return;
    // 向右拖动 → 右栏变窄 → 中栏变宽 → PDF 适应宽度后放大
    const next = d.startW - (e.clientX - d.startX);
    setRightWidth(Math.min(Math.max(next, d.min), d.max));
  }, []);

  const endDrag = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) return;
    dragRef.current = null;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
    document.body.classList.remove("col-resizing");
    // 收尾再校正一次，确保最终宽度下精确适配（拖拽中的去抖重排可能被取消）
    viewerRef.current?.refit();
  }, []);

  /** 窗口缩小时把右栏宽度收回可用范围，避免三栏溢出 */
  useEffect(() => {
    const onResize = () => {
      setRightWidth((w) => {
        if (w == null) return w;
        const main = mainRef.current;
        if (!main) return w;
        const max = Math.max(RIGHT_MIN, maxRightWidth(main));
        return Math.min(Math.max(w, Math.min(RIGHT_MIN, max)), max);
      });
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  /** 拖拽过则用显式宽度；中栏折叠时不施加（交给 .center-collapsed 铺满） */
  const rightPaneStyle = useMemo(
    () =>
      centerOpen && rightWidth != null
        ? { flex: `0 0 ${rightWidth}px`, width: `${rightWidth}px` }
        : undefined,
    [centerOpen, rightWidth],
  );

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

      <main ref={mainRef} className={`app-main${centerOpen ? "" : " center-collapsed"}`}>
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
        {centerOpen ? (
          <div
            className="edge-strip edge-strip-center edge-strip-drag"
            onPointerDown={beginDrag}
            onPointerMove={moveDrag}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
            onDoubleClick={() => setCenterOpen(false)}
            title="左右拖动可缩放文献预览（双击折叠）"
            role="separator"
            aria-orientation="vertical"
          >
            <span className="edge-strip-grip" />
          </div>
        ) : (
          <div
            className="sidebar-rail rail-center"
            onClick={() => setCenterOpen(true)}
            title="展开论文预览"
            role="button"
          >
            ‹
          </div>
        )}

        {rightOpen ? (
          <>
            <aside className="sidebar-right" style={rightPaneStyle}>
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
