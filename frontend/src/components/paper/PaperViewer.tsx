/* PaperViewer.tsx — 中间面板：PDF 阅读器 / 文本预览 */
import { useEffect, useRef } from "react";
import type { Paper } from "../../types";
import { PdfViewer, type PdfViewerHandle } from "./PdfViewer";
import { TextViewer } from "./TextViewer";

interface Props {
  paper: Paper | null;
  text: string;
  /** 外部（批注列表）请求定位到某条记录 → 已由结果表处理，无需跳页 */
  jumpToPage?: { page: number; token: number } | null;
}

export function PaperViewer({ paper, text, jumpToPage }: Props) {
  const pdfRef = useRef<PdfViewerHandle>(null);

  useEffect(() => {
    if (jumpToPage && paper?.has_pdf) {
      pdfRef.current?.jumpToPage(jumpToPage.page);
    }
  }, [jumpToPage, paper?.has_pdf]);

  return (
    <div className="paper-viewer-pane">
      {!paper && <div className="viewer-empty">从左侧选择一篇论文，或上传 PDF</div>}
      {paper && paper.has_pdf && <PdfViewer ref={pdfRef} paperId={paper.id} />}
      {paper && !paper.has_pdf && text && <TextViewer text={text} />}
      {paper && !paper.has_pdf && !text && <div className="viewer-loading">正在加载文本…</div>}
    </div>
  );
}
