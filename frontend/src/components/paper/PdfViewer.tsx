/* PdfViewer.tsx — pdf.js 论文阅读器（类似 Chrome PDF 预览）
 * - canvas 渲染 + TextLayer 文本层（可选可选中）
 * - 缩放（0.5–2.5 / 适应宽度）、页码导航（滚动联动）
 * - 文本选中 → onSelect 回调；批注高亮层按归一化 rect 渲染
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
import { pdfUrl } from "../../api/client";
import type { AnchorRect, Annotation, PendingSelection } from "../../types";

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

export interface PdfViewerHandle {
  jumpToPage: (page: number) => void;
}

interface Props {
  paperId: string;
  annotations: Annotation[];
  onSelect: (sel: PendingSelection) => void;
  onPageChange?: (page: number) => void;
}

const ZOOM_STEP = 0.15;
const MIN_SCALE = 0.5;
const MAX_SCALE = 2.5;

/* ---- 单页：canvas + 文本层 + 高亮层 ---- */
function PageView({
  pdf,
  pageNo,
  scale,
  annotations,
  onSelect,
}: {
  pdf: PDFDocumentProxy;
  pageNo: number;
  scale: number;
  annotations: Annotation[];
  onSelect: (sel: PendingSelection) => void;
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
      const viewport = page.getViewport({ scale });
      setSize({ w: viewport.width, h: viewport.height });

      const canvas = canvasRef.current;
      const textLayerDiv = textLayerRef.current;
      if (!canvas || !textLayerDiv) return;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      await page.render({ canvasContext: ctx, viewport }).promise;
      if (cancelled) return;

      const textContent = await page.getTextContent();
      if (cancelled) return;
      textLayerDiv.innerHTML = "";
      textLayerDiv.style.width = `${viewport.width}px`;
      textLayerDiv.style.height = `${viewport.height}px`;
      const textLayer = new pdfjsLib.TextLayer({
        textContentSource: textContent,
        container: textLayerDiv,
        viewport,
      });
      await textLayer.render();
    })().catch((e) => console.error(`page ${pageNo} render failed:`, e));
    return () => {
      cancelled = true;
      void page?.cleanup();
    };
  }, [pdf, pageNo, scale]);

  /* 文本选中 → 归一化 rects + 页码 */
  const handleMouseUp = useCallback(() => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.toString().trim()) return;
    const quote = sel.toString().trim();
    if (quote.length < 3) return;

    const range = sel.getRangeAt(0);
    const node =
      range.commonAncestorContainer instanceof Element
        ? range.commonAncestorContainer
        : range.commonAncestorContainer.parentElement;
    const shell = node?.closest("[data-page-number]") as HTMLElement | null;
    const holder = holderRef.current;
    if (!shell || !holder) return;

    const pr = holder.getBoundingClientRect();
    const rects: AnchorRect[] = Array.from(range.getClientRects()).map((r) => ({
      x: (r.left - pr.left) / pr.width,
      y: (r.top - pr.top) / pr.height,
      w: r.width / pr.width,
      h: r.height / pr.height,
    }));
    onSelect({ page: Number(shell.dataset.pageNumber), quote, rects });
    sel.removeAllRanges();
  }, [onSelect]);

  const pageAnnotations = annotations.filter((a) => a.page === pageNo);

  return (
    <div className="page-shell" data-page-number={pageNo}>
      <div className="page-container" ref={holderRef} style={size ? { width: size.w, height: size.h } : undefined}>
        <canvas ref={canvasRef} />
        <div className="textLayer" ref={textLayerRef} onMouseUp={handleMouseUp} />
        {size &&
          pageAnnotations.map((a) =>
            a.anchor.rects.map((r, i) => (
              <div
                key={`${a.id}-${i}`}
                className="annotation-highlight"
                data-annotation-id={a.id}
                style={{
                  left: `${r.x * 100}%`,
                  top: `${r.y * 100}%`,
                  width: `${r.w * 100}%`,
                  height: `${r.h * 100}%`,
                }}
              />
            )),
          )}
        <span className="page-label">{pageNo}</span>
      </div>
    </div>
  );
}

/* ---- 主组件 ---- */
export const PdfViewer = forwardRef<PdfViewerHandle, Props>(function PdfViewer(
  { paperId, annotations, onSelect, onPageChange },
  ref,
) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [pageCount, setPageCount] = useState(0);
  const [scale, setScale] = useState(1);
  const [currentPage, setCurrentPage] = useState(1);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fitScaleRef = useRef(1);

  /* 加载 PDF */
  useEffect(() => {
    let cancelled = false;
    const task = pdfjsLib.getDocument({
      url: pdfUrl(paperId),
      useWorkerFetch: false,
      isEvalSupported: false,
    });
    task.promise
      .then((doc) => {
        if (cancelled) {
          void doc.destroy();
          return;
        }
        setPdf(doc);
        setPageCount(doc.numPages);
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

  /* 适应宽度：以第一页为准 */
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

  useEffect(() => {
    onPageChange?.(currentPage);
  }, [currentPage, onPageChange]);

  useImperativeHandle(ref, () => ({
    jumpToPage(page: number) {
      const shell = scrollRef.current?.querySelector<HTMLElement>(
        `[data-page-number="${page}"]`,
      );
      shell?.scrollIntoView({ block: "start" });
    },
  }));

  const zoomIn = () => setScale((s) => Math.min(s + ZOOM_STEP, MAX_SCALE));
  const zoomOut = () => setScale((s) => Math.max(s - ZOOM_STEP, MIN_SCALE));

  return (
    <div className="pdf-viewer">
      <div className="viewer-toolbar">
        <button className="btn btn-sm" onClick={zoomOut} disabled={!pdf} title="缩小">
          −
        </button>
        <span className="zoom-label mono">{Math.round(scale * 100)}%</span>
        <button className="btn btn-sm" onClick={zoomIn} disabled={!pdf} title="放大">
          +
        </button>
        <button className="btn btn-sm" onClick={fitWidth} disabled={!pdf} title="适应宽度">
          适应
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
              annotations={annotations}
              onSelect={onSelect}
            />
          ))}
        {!pdf && <div className="viewer-loading">正在加载 PDF…</div>}
      </div>
    </div>
  );
});
