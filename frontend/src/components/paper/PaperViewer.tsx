/* PaperViewer.tsx — 中间面板：PDF 阅读器 / 文本预览
 * 同时作为"原文定位"中枢：App 通过 ref 调用 locate()，按论文类型分发到 PdfViewer 或 TextViewer。
 */
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import type { FieldHighlight, Paper } from "../../types";
import { PdfViewer, type PdfViewerHandle } from "./PdfViewer";
import { TextViewer, type TextViewerHandle } from "./TextViewer";

export interface PaperViewerHandle {
  jumpToPage: (page: number) => void;
  /** 原文定位：命中一组引用句 → 高亮 + 滚动；返回是否命中（PDF 为异步） */
  locate: (citations: string[], label: string) => Promise<boolean> | boolean;
  /** 提取过程动画：逐字段在原文上标注框选（PDF 为异步） */
  animateFields: (fields: FieldHighlight[]) => Promise<void>;
  /** 重新进入「适应宽度」模式（PDF 有效；纯文本无缩放概念） */
  refit: () => void;
}

interface Props {
  paper: Paper | null;
  text: string;
  /** 外部（批注列表）请求定位到某条记录 → 已由结果表处理，无需跳页 */
  jumpToPage?: { page: number; token: number } | null;
}

export const PaperViewer = forwardRef<PaperViewerHandle, Props>(function PaperViewer(
  { paper, text, jumpToPage },
  ref,
) {
  const pdfRef = useRef<PdfViewerHandle>(null);
  const textRef = useRef<TextViewerHandle>(null);

  useEffect(() => {
    if (jumpToPage && paper?.has_pdf) {
      pdfRef.current?.jumpToPage(jumpToPage.page);
    }
  }, [jumpToPage, paper?.has_pdf]);

  useImperativeHandle(
    ref,
    () => ({
      jumpToPage(page: number) {
        pdfRef.current?.jumpToPage(page);
      },
      locate(citations: string[], label: string) {
        if (paper?.has_pdf) {
          return pdfRef.current?.locateSentences(citations, label) ?? Promise.resolve(false);
        }
        return textRef.current?.locateSentences(citations, label) ?? false;
      },
      animateFields(fields: FieldHighlight[]) {
        if (paper?.has_pdf) {
          return pdfRef.current?.animateFields(fields) ?? Promise.resolve();
        }
        return textRef.current?.animateFields(fields) ?? Promise.resolve();
      },
      refit() {
        pdfRef.current?.refit();
      },
    }),
    [paper?.has_pdf],
  );

  return (
    <div className="paper-viewer-pane">
      {!paper && <div className="viewer-empty">从左侧选择一篇论文，或上传 PDF</div>}
      {paper && paper.has_pdf && <PdfViewer ref={pdfRef} paperId={paper.id} />}
      {paper && !paper.has_pdf && text && <TextViewer ref={textRef} text={text} />}
      {paper && !paper.has_pdf && !text && <div className="viewer-loading">正在加载文本…</div>}
    </div>
  );
});