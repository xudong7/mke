/* TextViewer.tsx — content.md 文本预览（无原始 PDF 的论文用），支持选中批注 */
import { useCallback, useRef } from "react";
import type { AnchorRect, PendingSelection } from "../../types";

interface Props {
  text: string;
  paperId: string;
  /** 用户选中文本 → 打开批注 */
  onSelect: (sel: PendingSelection) => void;
}

export function TextViewer({ text, onSelect }: Props) {
  const preRef = useRef<HTMLDivElement>(null);

  const handleMouseUp = useCallback(() => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.toString().trim()) return;
    const quote = sel.toString().trim();
    if (quote.length < 3) return;

    const range = sel.getRangeAt(0);
    const rects: AnchorRect[] = Array.from(range.getClientRects()).map((r) => ({
      x: 0,
      y: 0,
      w: r.width,
      h: r.height,
    }));

    onSelect({ page: null, quote, rects });
    sel.removeAllRanges();
  }, [onSelect]);

  return (
    <div className="text-viewer" onMouseUp={handleMouseUp}>
      <div className="text-viewer-paper" ref={preRef}>
        <pre>{text}</pre>
      </div>
    </div>
  );
}
