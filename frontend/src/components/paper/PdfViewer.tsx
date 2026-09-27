/* PdfViewer.tsx — pdf.js 论文阅读器（类似 Chrome PDF 预览）
 * - canvas 按 devicePixelRatio 渲染（高清屏清晰），TextLayer 用逻辑尺寸保持对齐
 * - 缩放（0.5–2.5 / 适应宽度，加载后默认适应宽度；侧栏折叠时自动重 fit）
 * - 页码导航（滚动联动）
 * - 原文定位（移植 mke-main index_v2）：locateSentences 匹配引用句并把命中段高亮 + 滚动
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
import type { FieldHighlight } from "../../types";

// ?v= 换缓存键：浏览器曾缓存过错误 MIME 的 worker 响应且难以清除，
// 改此版本号可强制所有客户端重新拉取 worker 文件
pdfjsLib.GlobalWorkerOptions.workerSrc = `${workerUrl}?v=2`;

export interface PdfViewerHandle {
  jumpToPage: (page: number) => void;
  /** 在 PDF 原文中定位一组引用句，找到第一句即高亮 + 滚动；返回是否命中 */
  locateSentences: (sentences: string[], label: string) => Promise<boolean>;
  /** 提取过程动画：按字段顺序在原文上逐段标注框选（先脉冲后转绿）；新调用会取消旧动画 */
  animateFields: (fields: FieldHighlight[]) => Promise<void>;
  /** 重新进入「适应宽度」模式并按当前容器宽度重排（拖动分隔条后调用） */
  refit: () => void;
}

interface Props {
  paperId: string;
}

const ZOOM_STEP = 0.15;
const MIN_SCALE = 0.5;
const MAX_SCALE = 2.5;
const DPR_CAP = 2;

/** pdf.js 文本项的子集类型（TextItem 未从包根导出，本地声明即可） */
interface PdfTextItem {
  str: string;
  width: number;
  height: number;
  transform: number[];
}

/* ---- 原文定位：归一化 + 最长公共子串匹配（移植 mke-main index_v2） ---- */

/** 归一化：小写 + 只保留字母数字（容忍 PDF 换行/连字符/大小写差异） */
function normalizeText(s: string): string {
  return String(s || "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

/** 最长公共子串（滚动数组 DP） */
function longestCommonSubstring(a: string, b: string): string {
  const la = a.length;
  const lb = b.length;
  let prev = new Array(lb + 1).fill(0);
  let maxLen = 0;
  let endA = 0;
  for (let i = 1; i <= la; i++) {
    const cur = new Array(lb + 1).fill(0);
    for (let j = 1; j <= lb; j++) {
      if (a[i - 1] === b[j - 1]) {
        cur[j] = prev[j - 1] + 1;
        if (cur[j] > maxLen) {
          maxLen = cur[j];
          endA = i;
        }
      } else {
        cur[j] = 0;
      }
    }
    prev = cur;
  }
  return a.slice(endA - maxLen, endA);
}

/** 单页索引：归一化串 + 每个字符对应的矩形（PDF 单位坐标，高亮时乘 scale） */
interface PageIndex {
  pageNo: number;
  norm: string;
  charToRect: Array<{ x: number; y: number; w: number; h: number }>;
}

interface Span {
  start: number;
  end: number;
  score: number;
  exact: boolean;
}

/** 已绘制的高亮：保留描述以便缩放/拖拽后按新 scale 重绘（box 会随重绘更新） */
interface DrawnHighlight {
  pageNo: number;
  span: Span;
  label: string;
  cls?: string;
  box?: HTMLElement | null;
}

/** 在单页中匹配引用句：先精确，再模糊（最长公共子串） */
function matchSpan(idx: PageIndex, cite: string): Span | null {
  if (!cite) return null;
  const exact = idx.norm.indexOf(cite);
  if (exact >= 0) return { start: exact, end: exact + cite.length, score: cite.length, exact: true };
  // 模糊：最长公共子串
  const lcs = longestCommonSubstring(idx.norm, cite);
  const minLen = Math.max(8, Math.floor(cite.length * 0.3));
  if (lcs.length >= minLen) {
    const s = idx.norm.indexOf(lcs);
    return { start: s, end: s + lcs.length, score: lcs.length, exact: false };
  }
  return null;
}

const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/* ---- 关键词兜底（移植 mke-main index_v2）：引用句缺失时按字段关键词定位原文 ---- */

/** 字段默认关键词（英文文献，用于提取动画的视觉定位，不参与结果正确性） */
const DEFAULT_KEYWORDS: Record<string, string[]> = {
  组装方式: ["sol-gel", "soft-template", "hydrothermal", "synthesis", "prepared", "synthesized", "Stöber"],
  溶剂体系: ["solvent", "water", "ethanol", "butanol", "solution", "DI water"],
  "pH值_酸碱浓度": ["acetic acid", "hydrochloric", "molar", "acid"],
  表面活性剂种类: ["P123", "F127", "CTAB", "pluronic", "surfactant", "template", "SDA"],
  表面活性剂浓度: ["concentration", "amount"],
  "硅/钛源种类_浓度": ["TEOS", "titanium", "silica", "precursor", "molar ratio"],
  盐种类_浓度: ["NaCl", "chloride", "salt", "molar"],
  合成温度: ["temperature", "calcined", "dried", "heated", "°C"],
  比表面积: ["surface area", "BET", "m2/g", "m²/g", "specific surface"],
  孔径: ["pore size", "pore diameter", "pore width", "BJH", "nm"],
  介孔结构: ["mesoporous", "hexagonal", "p6mm", "ordered", "structure", "wormhole"],
  产物形态: ["powder", "particles", "morphology", "nanoparticle"],
  其他变量: ["extraction", "washing", "calcination"],
};

const STOP_WORDS = new Set([
  "the", "and", "for", "was", "were", "are", "is", "in", "to", "of", "a", "an", "with",
  "from", "that", "this", "which", "have", "has", "had", "been", "but", "not", "you", "all",
  "can", "her", "one", "our", "out", "day", "get", "him", "his", "how", "its", "may", "new",
  "now", "old", "see", "way", "who", "did", "does", "let", "say", "she", "too", "use", "used",
  "using", "being",
]);

/** 从字段值里提取英文关键词（长度≥4 的单词 + 化学式/术语 + 带单位数值） */
function extractKeywords(text: string): string[] {
  const words = text.match(/[A-Za-z]{4,}/g) || [];
  const chemTerms = text.match(/\b(TEOS|P123|F127|CTAB|BET|BJH|SBA|MCM|TiO2|SiO2)\b/gi) || [];
  const values = text.match(/\d+\.?\s*(°C|m2\/g|m²\/g|nm|wt%)/g) || [];
  const allTerms = [...new Set([...words, ...chemTerms, ...values])];
  return allTerms.filter((w) => !STOP_WORDS.has(w.toLowerCase())).slice(0, 8);
}

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

  // 原文定位状态（用 ref 避免闭包过期）
  const pageIndexRef = useRef<Map<number, PageIndex>>(new Map());
  const pdfRef = useRef<PDFDocumentProxy | null>(null);
  const scaleRef = useRef(scale);
  const pageCountRef = useRef(0);
  /** 动画取消令牌：新动画开始时自增，旧动画在下一次 await 后据此退出 */
  const animateTokenRef = useRef(0);
  /** 已绘制的高亮描述：缩放/拖拽使页面重挂载后按新 scale 重绘，保证定位结果不消失 */
  const drawnRef = useRef<DrawnHighlight[]>([]);
  useEffect(() => {
    scaleRef.current = scale;
  }, [scale]);
  useEffect(() => {
    pdfRef.current = pdf;
    pageCountRef.current = pageCount;
  }, [pdf, pageCount]);

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
        pageCountRef.current = doc.numPages;
        pageIndexRef.current = new Map(); // 换论文清空索引
        drawnRef.current = []; // 换论文清空已记录的高亮
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

  /* 侧栏折叠/拖动分隔条/窗口变化时：仍在 fit 模式则自动重排 */
  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    let timer: number | undefined;
    const observer = new ResizeObserver(() => {
      if (fitScaleRef.current === null || Math.abs(scale - fitScaleRef.current) >= 0.001) return;
      // 拖动分隔条会连续触发尺寸变化；去抖后只重排一次，
      // 否则每帧都会 setScale → 整篇页面按新 key 重建（含 canvas 重绘与文本层重建）
      window.clearTimeout(timer);
      timer = window.setTimeout(() => void fitWidth(), 120);
    });
    observer.observe(container);
    return () => {
      window.clearTimeout(timer);
      observer.disconnect();
    };
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

  /* ---- 原文定位实现 ---- */

  /** 懒构建单页文本索引（PDF 单位坐标，缩放无关） */
  const getPageIndex = useCallback(
    async (pageNo: number): Promise<PageIndex | null> => {
      const cached = pageIndexRef.current.get(pageNo);
      if (cached) return cached;
      const doc = pdfRef.current;
      if (!doc) return null;
      const page = await doc.getPage(pageNo);
      const textContent = await page.getTextContent();
      const vp = page.getViewport({ scale: 1 });
      let norm = "";
      const charToRect: PageIndex["charToRect"] = [];
      for (const it of textContent.items) {
        const item = it as PdfTextItem;
        if (!item.str) continue;
        const cleaned = normalizeText(item.str);
        if (!cleaned) continue;
        const h = item.height > 0 ? item.height : 12;
        const rect = {
          x: item.transform[4],
          y: vp.height - (item.transform[5] + h),
          w: item.width,
          h,
        };
        for (let i = 0; i < cleaned.length; i++) {
          norm += cleaned[i];
          charToRect.push(rect);
        }
      }
      const idx: PageIndex = { pageNo, norm, charToRect };
      pageIndexRef.current.set(pageNo, idx);
      return idx;
    },
    [],
  );

  /** 只清除高亮框 DOM（保留描述，便于缩放后重绘） */
  const clearHighlightDom = useCallback(() => {
    scrollRef.current
      ?.querySelectorAll<HTMLElement>(".highlight-box")
      .forEach((el) => el.remove());
  }, []);

  /** 清除 DOM 并丢弃描述（新一轮定位/动画开始时调用） */
  const resetHighlights = useCallback(() => {
    clearHighlightDom();
    drawnRef.current = [];
  }, [clearHighlightDom]);

  /** 跨页定位引用句：精确命中优先，否则取全篇最相似处 */
  const locateCitationText = useCallback(
    async (citation: string): Promise<{ pageNo: number; span: Span } | null> => {
      const cite = normalizeText(citation);
      if (!cite || !pdfRef.current) return null;
      let best: { pageNo: number; span: Span } | null = null;
      for (let p = 1; p <= pageCountRef.current; p++) {
        const idx = await getPageIndex(p);
        if (!idx) continue;
        const span = matchSpan(idx, cite);
        if (!span) continue;
        if (span.exact) return { pageNo: p, span };
        if (!best || span.score > best.span.score) best = { pageNo: p, span };
      }
      return best;
    },
    [getPageIndex],
  );

  /** 命中段 → 高亮框（坐标 × 当前缩放，与 textLayer 逻辑尺寸对齐） */
  const drawHighlight = useCallback(
    (pageNo: number, span: Span, label: string): HTMLElement | null => {
      const idx = pageIndexRef.current.get(pageNo);
      if (!idx) return null;
      const rects = idx.charToRect.slice(span.start, span.end);
      if (!rects.length) return null;
      const s = scaleRef.current;
      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;
      for (const r of rects) {
        minX = Math.min(minX, r.x * s);
        minY = Math.min(minY, r.y * s);
        maxX = Math.max(maxX, (r.x + r.w) * s);
        maxY = Math.max(maxY, (r.y + r.h) * s);
      }
      if (!Number.isFinite(minX)) return null;
      const pad = 3;
      const container = scrollRef.current?.querySelector<HTMLElement>(
        `[data-page-number="${pageNo}"] .page-container`,
      );
      if (!container) return null;
      const box = document.createElement("div");
      box.className = "highlight-box";
      box.style.left = `${minX - pad}px`;
      box.style.top = `${minY - pad}px`;
      box.style.width = `${maxX - minX + pad * 2}px`;
      box.style.height = `${maxY - minY + pad * 2}px`;
      const tip = document.createElement("div");
      tip.className = "tooltip";
      tip.textContent = label;
      box.appendChild(tip);
      container.appendChild(box);
      return box;
    },
    [],
  );

  /** 绘制高亮并记录描述（缩放/拖拽后据此重绘） */
  const drawRemembered = useCallback(
    (pageNo: number, span: Span, label: string): DrawnHighlight => {
      const rec: DrawnHighlight = { pageNo, span, label, box: null };
      rec.box = drawHighlight(pageNo, span, label);
      drawnRef.current.push(rec);
      return rec;
    },
    [drawHighlight],
  );

  /**
   * 只滚动 pdf 容器自身，把元素带到指定位置。
   *
   * 【不要用 el.scrollIntoView()】：它会连同所有可滚动祖先一起滚，包括 body。
   * 而 body 是 overflow:hidden —— 被程序化滚下去之后用户再也滚不回来，
   * 顶栏就被永久顶出视口（实测 body.scrollTop=22、顶栏 top=-22）。
   */
  const scrollElementIntoContainer = useCallback(
    (el: HTMLElement | null | undefined, align: "center" | "start" = "center") => {
      const container = scrollRef.current;
      if (!container || !el || !el.isConnected) return;
      const c = container.getBoundingClientRect();
      const b = el.getBoundingClientRect();
      const offset =
        align === "center" ? b.top - c.top - (c.height - b.height) / 2 : b.top - c.top;
      container.scrollTo({
        top: Math.max(0, container.scrollTop + offset),
        behavior: "smooth",
      });
    },
    [],
  );

  /**
   * 把高亮框滚到视口内（单次滚动）。
   * 框已经在视口内时【完全不动】——动画逐字段播放时，若每个字段都先滚到页顶
   * 再回到框居中，画面就会在两个位置之间反复摇摆。
   */
  const scrollBoxIntoView = useCallback(
    (box: HTMLElement | null | undefined) => {
      const container = scrollRef.current;
      if (!container || !box || !box.isConnected) return;
      const c = container.getBoundingClientRect();
      const b = box.getBoundingClientRect();
      const margin = 60;
      if (b.top >= c.top + margin && b.bottom <= c.bottom - margin) return; // 已可见，不动
      scrollElementIntoContainer(box, "center");
    },
    [scrollElementIntoContainer],
  );

  /** 定位后：滚动到高亮框（单次滚动）并闪烁 */
  const scrollToHighlight = useCallback(
    (box: HTMLElement) => {
      if (!box.isConnected) return;
      scrollElementIntoContainer(box, "center");
      box.classList.add("active");
      window.setTimeout(() => {
        box.classList.remove("active");
        box.classList.add("done");
      }, 5000);
    },
    [scrollElementIntoContainer],
  );

  /** 关键词兜底：字段无引用句时，用默认关键词 + 值内英文关键词跨页定位 */
  const searchKeywords = useCallback(
    async (field: string, value?: string): Promise<{ pageNo: number; span: Span } | null> => {
      const keywords = [
        ...(extractKeywords(value ?? "") || []),
        ...(DEFAULT_KEYWORDS[field] ?? []),
      ].filter(Boolean);
      for (const kw of [...new Set(keywords)]) {
        const hit = await locateCitationText(kw);
        if (hit) return hit;
      }
      return null;
    },
    [locateCitationText],
  );

  const locateSentences = useCallback(
    async (sentences: string[], label: string): Promise<boolean> => {
      if (!pdfRef.current) return false;
      resetHighlights();
      for (const sentence of sentences) {
        if (!sentence) continue;
        const hit = await locateCitationText(sentence);
        if (!hit) continue;
        const rec = drawRemembered(hit.pageNo, hit.span, label);
        if (rec.box) {
          scrollToHighlight(rec.box);
          return true;
        }
      }
      // 引用句未命中 → 字段关键词兜底（对齐 mke-main index_v2 的 locateField）
      const kwHit = await searchKeywords(label);
      if (kwHit) {
        const rec = drawRemembered(kwHit.pageNo, kwHit.span, label);
        if (rec.box) {
          scrollToHighlight(rec.box);
          return true;
        }
      }
      return false;
    },
    [resetHighlights, locateCitationText, searchKeywords, drawRemembered, scrollToHighlight],
  );

  /** 提取过程动画：逐字段在原文上标注框选（先脉冲 active，再转绿 done） */
  const animateFields = useCallback(
    async (fields: FieldHighlight[]): Promise<void> => {
      if (!pdfRef.current) return;
      const token = ++animateTokenRef.current;
      resetHighlights();
      for (const f of fields) {
        if (token !== animateTokenRef.current) return;
        const label = f.field;
        let hit: { pageNo: number; span: Span } | null = null;
        const sentences = (f.sentences ?? []).filter((s) => normalizeText(s).length > 0);
        for (const s of sentences) {
          hit = await locateCitationText(s);
          if (hit) break;
        }
        if (token !== animateTokenRef.current) return;
        if (!hit) hit = await searchKeywords(label, f.value);
        if (!hit) continue;
        const rec = drawRemembered(hit.pageNo, hit.span, label);
        if (!rec.box) continue;

        // 单次滚动：框已在视口内就不动，避免整段动画反复上下摇摆
        scrollBoxIntoView(rec.box);
        rec.cls = "active";
        rec.box.classList.add("active");
        await delay(700);
        if (token !== animateTokenRef.current) return;
        // 期间若发生缩放重绘，rec.box 已被替换 → 这里读最新节点，避免对已卸载的旧节点改类名
        if (rec.box?.isConnected) {
          rec.cls = "done";
          rec.box.classList.remove("active");
          rec.box.classList.add("done");
        }
        await delay(180);
      }
    },
    [resetHighlights, locateCitationText, searchKeywords, drawRemembered, scrollBoxIntoView],
  );

  /* 缩放/拖拽改变 scale 时 PageView 会按新 key 重建（旧的高亮框随之销毁），
     此处按当前 scale 重绘已记录的高亮，使拖动分隔条后定位结果依然可见。 */
  useEffect(() => {
    if (!pdf) return;
    clearHighlightDom();
    for (const h of drawnRef.current) {
      h.box = drawHighlight(h.pageNo, h.span, h.label);
      if (h.box && h.cls) h.box.classList.add(h.cls);
    }
  }, [scale, pdf, clearHighlightDom, drawHighlight]);

  useImperativeHandle(
    ref,
    () => ({
      jumpToPage(page: number) {
        const shell = scrollRef.current?.querySelector<HTMLElement>(
          `[data-page-number="${page}"]`,
        );
        scrollElementIntoContainer(shell, "start");
      },
      locateSentences,
      animateFields,
      refit: () => void fitWidth(),
    }),
    [locateSentences, animateFields, fitWidth, scrollElementIntoContainer],
  );

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
        <button className="btn btn-sm" onClick={zoomOut} disabled={!pdf} title="缩小">
          −
        </button>
        <span className="zoom-label mono">{Math.round(scale * 100)}%</span>
        <button className="btn btn-sm" onClick={zoomIn} disabled={!pdf} title="放大">
          +
        </button>
        <button
          className="btn btn-sm"
          onClick={() => void fitWidth()}
          disabled={!pdf}
          title="适应宽度"
        >
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
            />
          ))}
        {!pdf && <div className="viewer-loading">正在加载 PDF…</div>}
      </div>
    </div>
  );
});