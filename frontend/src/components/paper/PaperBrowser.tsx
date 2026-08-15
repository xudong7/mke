/* PaperBrowser.tsx — 左面板：论文列表 + PDF 阅读器 / 文本预览 */
import { useEffect, useRef } from "react";
import type { Annotation, Paper, PendingSelection } from "../../types";
import { PaperList } from "./PaperList";
import { PdfViewer, type PdfViewerHandle } from "./PdfViewer";
import { TextViewer } from "./TextViewer";

interface Props {
  papers: Paper[];
  selected: Paper | null;
  /** 论文解析文本（懒加载，可能为空） */
  text: string;
  annotations: Annotation[];
  onSelectPaper: (p: Paper) => void;
  onUploaded: () => void;
  onSelectText: (sel: PendingSelection) => void;
  /** 批注列表点击 → 跳转到 PDF 对应页 */
  onJumpRequest: { page: number; token: number } | null;
}

export function PaperBrowser({
  papers,
  selected,
  text,
  annotations,
  onSelectPaper,
  onUploaded,
  onSelectText,
  onJumpRequest,
}: Props) {
  const pdfRef = useRef<PdfViewerHandle>(null);

  // 外部（批注列表）请求跳页
  useEffect(() => {
    if (onJumpRequest && selected?.has_pdf) {
      pdfRef.current?.jumpToPage(onJumpRequest.page);
    }
  }, [onJumpRequest, selected?.has_pdf]);

  return (
    <div className="paper-browser">
      <PaperList
        papers={papers}
        selectedId={selected?.id ?? null}
        onSelect={onSelectPaper}
        onUploaded={onUploaded}
      />
      <div className="paper-viewer-pane">
        {!selected && <div className="viewer-empty">从左侧选择一篇论文，或上传 PDF</div>}
        {selected && selected.has_pdf && (
          <PdfViewer
            ref={pdfRef}
            paperId={selected.id}
            annotations={annotations}
            onSelect={onSelectText}
          />
        )}
        {selected && !selected.has_pdf && text && (
          <TextViewer text={text} paperId={selected.id} onSelect={onSelectText} />
        )}
        {selected && !selected.has_pdf && !text && (
          <div className="viewer-loading">正在加载文本…</div>
        )}
      </div>
    </div>
  );
}
