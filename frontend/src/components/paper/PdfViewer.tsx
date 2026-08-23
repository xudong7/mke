/* PdfViewer.tsx — pdf.js 论文阅读器（类似 Chrome PDF 预览）
 * - canvas 按 devicePixelRatio 渲染（高清屏清晰），TextLayer 用逻辑尺寸保持对齐
 * - 缩放（0.5–2.5 / 适应宽度，加载后默认适应宽度；侧栏折叠时自动重 fit）
 * - 页码导航（滚动联动）
 */
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import * as pdfjsLib from "pdfjs-dist";
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { Maximize, ZoomIn, ZoomOut } from "lucide-react";
import { pdfUrl } from "../../api/client";

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

export interface PdfViewerHandle {
  jumpToPage: (page: number) => void;
}

interface Props {
  paperId: string;
}

const ZOOM_STEP = 0.15;
const MIN_SCALE = 0.5;
const MAX_SCALE = 2.5;
const DPR_CAP = 2;

/* ---- 单页：canvas（DPR 高清）+ 文本层（逻辑尺寸） ---- */
function PageView({
  pdf,
  pageNo,
  scale,
}: {
  pdf: PDFDocumentProxy;
  pageNo: number;
  scale: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textLayerRef = useRef<HTMLDivElement>(null);
  const holderRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    let page: PDFPageProxy | null = null;
    (async () => {
      page = await pdf.getPage(pageNo);
      if (cancelled) return;

      // 双 viewport：canvas 用 scale×dpr（高清），布局/文本层用逻辑 scale
      const dpr = Math.min(window.devicePixelRatio || 1, DPR_CAP);
      const renderViewport = page.getViewport({ scale: scale * dpr });
      const cssViewport = page.getViewport({ scale });
      setSize({ w: cssViewport.width, h: cssViewport.height });

      const canvas = canvasRef.current;
      const textLayerDiv = textLayerRef.current;
      if (!canvas || !textLayerDiv) return;
      canvas.width = Math.floor(renderViewport.width);
      canvas.height = Math.floor(renderViewport.height);
      canvas.style.width = `${Math.floor(renderViewport.width / dpr)}px`;
      canvas.style.height = `${Math.floor(renderViewport.height / dpr)}px`;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      await page.render({ canvasContext: ctx, viewport: renderViewport }).promise;
      if (cancelled) return;

      const textContent = await page.getTextContent();
      if (cancelled) return;
      textLayerDiv.innerHTML = "";
      textLayerDiv.style.width = `${cssViewport.width}px`;
      textLayerDiv.style.height = `${cssViewport.height}px`;
      const textLayer = new pdfjsLib.TextLayer({
        textContentSource: textContent,
        container: textLayerDiv,
        viewport: cssViewport,
      });
      await textLayer.render();
    })().catch((e) => console.error(`page ${pageNo} render failed:`, e));
    return () => {
      cancelled = true;
      void page?.cleanup();
    };
  }, [pdf, pageNo, scale]);

  return (
    <div className="page-shell" data-page-number={pageNo}>
      <div
        className="page-container"
        ref={holderRef}
        style={size ? { width: size.w, height: size.h } : undefined}
      >
        <canvas ref={canvasRef} />
        <div className="textLayer" ref={textLayerRef} />
        <span className="page-label">{pageNo}</span>
      </div>
    </div>
  );
}

/* ---- 主组件 ---- */
export const PdfViewer = forwardRef<PdfViewerHandle, Props>(function PdfViewer({ paperId }, ref) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [pageCount, setPageCount] = useState(0);
  const [scale, setScale] = useState(1);
  const [currentPage, setCurrentPage] = useState(1);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fitScaleRef = useRef<number | null>(null);

  /* 加载 PDF → 默认适应宽度 */
  useEffect(() => {
    let cancelled = false;
    const task = pdfjsLib.getDocument({
      url: pdfUrl(paperId),
      useWorkerFetch: false,
      isEvalSupported: false,
    });
    task.promise
      .then(async (doc) => {
        if (cancelled) {
          void doc.destroy();
          return;
        }
        setPdf(doc);
        setPageCount(doc.numPages);
        // 等待布局就绪后按容器宽度 fit
        requestAnimationFrame(() => {
          const container = scrollRef.current;
          if (!container) return;
          const page1 = doc.getPage(1);
          void page1.then((p) => {
            const base = p.getViewport({ scale: 1 });
            const available = Math.max(container.clientWidth - 48, 300);
            const s = Math.min(Math.max(available / base.width, MIN_SCALE), MAX_SCALE);
            fitScaleRef.current = s;
            setScale(s);
            void p.cleanup();
          });
        });
      })
      .catch((e) => console.error("pdf load failed:", e));
    return () => {
      cancelled = true;
      setPdf((prev) => {
        void prev?.destroy();
        return null;
      });
    };
  }, [paperId]);

  /* 适应宽度 */
  const fitWidth = useCallback(async () => {
    if (!pdf) return;
    const container = scrollRef.current;
    if (!container) return;
    const page = await pdf.getPage(1);
    const base = page.getViewport({ scale: 1 });
    const available = Math.max(container.clientWidth - 48, 300);
    const s = Math.min(Math.max(available / base.width, MIN_SCALE), MAX_SCALE);
    fitScaleRef.current = s;
    setScale(s);
  }, [pdf]);

  /* 侧栏折叠/窗口变化时：仍在 fit 模式则自动重排 */
  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const observer = new ResizeObserver(() => {
      if (fitScaleRef.current !== null && Math.abs(scale - fitScaleRef.current) < 0.001) {
        void fitWidth();
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [scale, fitWidth]);

  /* 滚动联动 currentPage */
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const shells = el.querySelectorAll<HTMLElement>(".page-shell");
      const viewportTop = el.scrollTop + 80;
      let current = 1;
      shells.forEach((shell) => {
        if (shell.offsetTop <= viewportTop) current = Number(shell.dataset.pageNumber);
      });
      setCurrentPage(current);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [pdf]);

  useImperativeHandle(ref, () => ({
    jumpToPage(page: number) {
      const shell = scrollRef.current?.querySelector<HTMLElement>(
        `[data-page-number="${page}"]`,
      );
      shell?.scrollIntoView({ block: "start" });
    },
  }));

  const zoomIn = () => {
    fitScaleRef.current = null; // 手动缩放脱离 fit 模式
    setScale((s) => Math.min(s + ZOOM_STEP, MAX_SCALE));
  };
  const zoomOut = () => {
    fitScaleRef.current = null;
    setScale((s) => Math.max(s - ZOOM_STEP, MIN_SCALE));
  };

  return (
    <div className="pdf-viewer">
      <div className="viewer-toolbar">
        <button className="btn btn-icon" onClick={zoomOut} disabled={!pdf} aria-label="缩小" title="缩小">
          <ZoomOut size={14} />
        </button>
        <span className="zoom-label mono">{Math.round(scale * 100)}%</span>
        <button className="btn btn-icon" onClick={zoomIn} disabled={!pdf} aria-label="放大" title="放大">
          <ZoomIn size={14} />
        </button>
        <button
          className="btn btn-icon"
          onClick={() => void fitWidth()}
          disabled={!pdf}
          aria-label="适应宽度"
          title="适应宽度"
        >
          <Maximize size={14} />
        </button>
        <span className="toolbar-spacer" />
        <span className="page-nav mono">
          {currentPage} / {pageCount || "–"}
        </span>
      </div>
      <div className="pdf-scroll" ref={scrollRef}>
        {pdf &&
          Array.from({ length: pageCount }, (_, i) => (
            <PageView
              key={`${paperId}-${i + 1}-${scale}`}
              pdf={pdf}
              pageNo={i + 1}
              scale={scale}
            />
          ))}
        {!pdf && <div className="viewer-loading">正在加载 PDF…</div>}
      </div>
    </div>
  );
});
