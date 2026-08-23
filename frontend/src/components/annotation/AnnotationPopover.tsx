/* AnnotationPopover.tsx — 批注输入浮层（点击结果行/字段后弹出，不占布局） */
import { Check, X } from "lucide-react";
import type { AnnotationTarget } from "../pipeline/ResultsTable";

interface Props {
  target: AnnotationTarget;
  /** 触发按钮的视口坐标（弹层锚点） */
  anchor: { x: number; y: number };
  note: string;
  onNoteChange: (v: string) => void;
  onSave: () => void;
  onCancel: () => void;
}

const WIDTH = 300;
const ESTIMATED_HEIGHT = 260;

export function AnnotationPopover({
  target,
  anchor,
  note,
  onNoteChange,
  onSave,
  onCancel,
}: Props) {
  // 视口内钳制：下方放不下则翻到上方
  const left = Math.max(8, Math.min(anchor.x - WIDTH / 2, window.innerWidth - WIDTH - 8));
  const top =
    anchor.y + 8 > window.innerHeight - ESTIMATED_HEIGHT
      ? Math.max(anchor.y - ESTIMATED_HEIGHT - 8, 8)
      : anchor.y + 8;

  return (
    <>
      <div className="annotation-popover-backdrop" onClick={onCancel} />
      <div className="annotation-popover card" style={{ left, top }}>
        <div className="annotation-editor">
          <div className="editor-label mono text-2">
            记录 #{target.record_index + 1}
            {target.field ? ` · ${target.field}` : ""}
          </div>
          {target.value_snapshot && (
            <div className="editor-quote">
              <blockquote className="mono">{target.value_snapshot}</blockquote>
            </div>
          )}
          <textarea
            value={note}
            onChange={(e) => onNoteChange(e.target.value)}
            placeholder="批注内容（原结果不会被修改）…"
            rows={3}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Escape") onCancel();
            }}
          />
          <div className="editor-actions">
            <button className="btn btn-icon" onClick={onCancel} aria-label="取消" title="关闭批注编辑">
              <X size={14} />
            </button>
            <button
              className="btn btn-sm btn-primary"
              onClick={onSave}
              disabled={!note.trim()}
            >
              <Check size={14} />
              保存批注
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
