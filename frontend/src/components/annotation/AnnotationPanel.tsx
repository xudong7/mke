/* AnnotationPanel.tsx — 批注交互区：选中文本 → 编辑批注；批注列表（跳页/删除） */
import { useState } from "react";
import type { Annotation, PendingSelection } from "../../types";

interface Props {
  /** 当前选中文本（来自左侧查看器） */
  selection: PendingSelection | null;
  annotations: Annotation[];
  onSave: (note: string) => Promise<void>;
  onCancel: () => void;
  onDelete: (id: string) => Promise<void>;
  /** 点击批注 → 跳转到 PDF 对应页 */
  onJump: (page: number) => void;
}

export function AnnotationPanel({
  selection,
  annotations,
  onSave,
  onCancel,
  onDelete,
  onJump,
}: Props) {
  const [note, setNote] = useState("");

  const handleSave = async () => {
    await onSave(note);
    setNote("");
  };

  return (
    <div className="annotation-panel">
      <div className="annotation-header">
        <span>批注</span>
        <span className="mono text-2">{annotations.length} 条</span>
      </div>

      {selection && (
        <div className="annotation-editor card">
          <div className="editor-quote">
            <span className="editor-label">选中原文（第 {selection.page ?? "—"} 页）</span>
            <blockquote className="mono">{selection.quote}</blockquote>
          </div>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="输入批注内容…（留空则仅保存原文引用）"
            rows={3}
          />
          <div className="editor-actions">
            <button className="btn btn-sm" onClick={onCancel}>
              取消
            </button>
            <button className="btn btn-sm btn-primary" onClick={handleSave}>
              保存批注
            </button>
          </div>
        </div>
      )}

      <div className="annotation-list">
        {annotations.length === 0 && !selection && (
          <div className="annotation-empty">在左侧论文中选中文本即可添加批注</div>
        )}
        {annotations.map((a) => (
          <div key={a.id} className="annotation-item card">
            <div className="annotation-item-head">
              <span className="mono text-2">
                {a.page ? `第 ${a.page} 页` : "文本预览"} ·{" "}
                {new Date(a.created_at).toLocaleString()}
              </span>
              <div className="annotation-item-actions">
                {a.page && (
                  <button className="btn btn-sm" onClick={() => onJump(a.page as number)}>
                    跳页
                  </button>
                )}
                <button className="btn btn-sm btn-danger-ghost" onClick={() => void onDelete(a.id)}>
                  删除
                </button>
              </div>
            </div>
            <div className="annotation-item-quote mono">“{a.quote}”</div>
            {a.note && <div className="annotation-item-note">{a.note}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
