/* TextViewer.tsx — content.md 文本预览（无原始 PDF 的论文用）
 * 支持原文定位：locateSentences 在全文命中引用句并用 <mark> 高亮 + 滚动
 */
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import type { FieldHighlight } from "../../types";

export interface TextViewerHandle {
  /** 在全文定位一组引用句，命中第一句即高亮 + 滚动；返回是否命中 */
  locateSentences: (sentences: string[], label: string) => boolean;
  /** 提取过程动画：按字段顺序在全文逐段闪烁高亮 */
  animateFields: (fields: FieldHighlight[]) => Promise<void>;
}

interface Flash {
  start: number;
  end: number;
}

const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export const TextViewer = forwardRef<TextViewerHandle, { text: string }>(function TextViewer(
  { text },
  ref,
) {
  const [flash, setFlash] = useState<Flash | null>(null);
  const flashSeq = useRef(0);
  const preRef = useRef<HTMLPreElement>(null);

  // 归一化索引：norm + 与原文逐字符对齐的原始下标（用于把归一化命中映射回原文 offset）
  const normIndex = useMemo(() => {
    let norm = "";
    const rawIdx: number[] = [];
    for (let i = 0; i < text.length; i++) {
      const ch = text[i].toLowerCase();
      if (/[a-z0-9]/.test(ch)) {
        norm += ch;
        rawIdx.push(i);
      }
    }
    return { norm, rawIdx };
  }, [text]);

  const findSpan = useCallback(
    (sentence: string): Flash | null => {
      if (!sentence) return null;
      // 1) 精确原始子串命中
      const exact = text.indexOf(sentence);
      if (exact >= 0) return { start: exact, end: exact + sentence.length };
      // 2) 归一化匹配并映射回原始 offset（容忍换行/连字符/大小写）
      let cite = "";
      for (let i = 0; i < sentence.length; i++) {
        const ch = sentence[i].toLowerCase();
        if (/[a-z0-9]/.test(ch)) cite += ch;
      }
      if (!cite) return null;
      const idx = normIndex.norm.indexOf(cite);
      if (idx < 0) return null;
      const start = normIndex.rawIdx[idx];
      const end = normIndex.rawIdx[idx + cite.length - 1] + 1;
      return { start, end: Math.min(end, text.length) };
    },
    [text, normIndex],
  );

  const locateSentences = useCallback(
    (sentences: string[], _label: string): boolean => {
      for (const s of sentences) {
        const span = findSpan(s);
        if (span) {
          setFlash(span);
          const seq = ++flashSeq.current;
          setTimeout(() => {
            if (flashSeq.current === seq) setFlash(null);
          }, 6000);
          return true;
        }
      }
      return false;
    },
    [findSpan],
  );

  const animateFields = useCallback(
    async (fields: FieldHighlight[]): Promise<void> => {
      flashSeq.current++; // 使 locateSentences 遗留的自动清除失效
      for (const f of fields) {
        const sentences = (f.sentences ?? []).filter(Boolean);
        let span: Flash | null = null;
        for (const s of sentences) {
          span = findSpan(s);
          if (span) break;
        }
        if (!span) continue;
        setFlash(span);
        await delay(1100);
      }
      setFlash(null);
    },
    [findSpan],
  );

  useImperativeHandle(ref, () => ({ locateSentences, animateFields }), [
    locateSentences,
    animateFields,
  ]);

  // 命中后滚动到高亮处
  useEffect(() => {
    if (!flash) return;
    const mark = document.querySelector<HTMLElement>("mark[data-flash]");
    mark?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [flash]);

  // 分段渲染（含临时高亮）
  const segments = useMemo(() => {
    if (!flash) return null;
    return [
      text.slice(0, flash.start),
      text.slice(flash.start, flash.end),
      text.slice(flash.end),
    ];
  }, [text, flash]);

  return (
    <div className="text-viewer">
      <div className="text-viewer-paper">
        <pre ref={preRef}>
          {segments ? (
            <>
              {segments[0]}
              <mark data-flash className="text-flash">
                {segments[1]}
              </mark>
              {segments[2]}
            </>
          ) : (
            text
          )}
        </pre>
      </div>
    </div>
  );
});