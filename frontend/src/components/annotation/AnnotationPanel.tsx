/* AnnotationPanel.tsx v2 — 结果批注列表：显示 (记录 #n, 字段, value_snapshot, note)，点击定位到记录 */
import { Trash2 } from "lucide-react";
import type { Annotation } from "../../types";

interface Props {
  annotations: Annotation[];
  onDelete: (id: string) => Promise<void>;
  onJumpToRecord: (index: number) => void;
}

export function AnnotationPanel({ annotations, onDelete, onJumpToRecord }: Props) {
  return (
    <div className="annotation-panel">
      <div className="annotation-header">
        <span>结果批注</span>
        <span className="mono text-2">{annotations.length} 条</span>
      </div>
      <div className="annotation-list">
        {annotations.length === 0 && (
          <div className="annotation-empty">
            运行流水线后，可在结果表中为记录或字段添加批注（点击查看批注原文）。
          </div>
        )}
        {annotations.map((a) => (
          <div
            key={a.id}
            className="annotation-item card"
            onClick={() => onJumpToRecord(a.record_index)}
            title="点击定位到对应记录"
          >
            <div className="annotation-item-head">
              <span className="mono text-2">
                记录 #{a.record_index + 1}
                {a.field ? ` · ${a.field}` : ""}
              </span>
              <div className="annotation-item-actions">
                <button
                  className="btn btn-icon btn-danger-ghost"
                  onClick={(e) => {
                    e.stopPropagation();
                    void onDelete(a.id);
                  }}
                  aria-label="删除"
                  title="删除该批注"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
            {a.value_snapshot && (
              <div className="annotation-item-quote mono">“{a.value_snapshot}”</div>
            )}
            {a.note && <div className="annotation-item-note">{a.note}</div>}
            <div className="annotation-item-time mono text-2">
              {new Date(a.created_at).toLocaleString()}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
