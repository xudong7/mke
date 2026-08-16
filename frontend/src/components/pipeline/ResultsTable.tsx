/* ResultsTable.tsx — 抽取结果表：关键列 + 行/字段级批注（hover 触发 + 浮层，不改原结果） */
import { useEffect, useState } from "react";
import type { Annotation, ExtractRecord } from "../../types";
import { AnnotationPopover } from "../annotation/AnnotationPopover";

const COLUMNS: string[] = [
  "分析类型",
  "组装方式",
  "表面活性剂种类",
  "表面活性剂浓度",
  "合成温度",
  "介孔结构",
  "比表面积",
  "孔径",
  "产物形态",
];

/** 批注目标（记录级或字段级） */
export interface AnnotationTarget {
  record_index: number;
  field?: string | null;
  value_snapshot?: string | null;
}

interface Props {
  records: ExtractRecord[];
  annotations: Annotation[];
  onSaveAnnotation: (target: AnnotationTarget, note: string) => Promise<void>;
  recordJump: { index: number; token: number } | null;
}

function cellText(v: unknown): string {
  if (v == null) return "00";
  return String(v).slice(0, 120);
}

export function ResultsTable({ records, annotations, onSaveAnnotation, recordJump }: Props) {
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [flashIdx, setFlashIdx] = useState<number | null>(null);
  const [popover, setPopover] = useState<{
    target: AnnotationTarget;
    anchor: { x: number; y: number };
  } | null>(null);

  /* 批注列表点击 → 滚动到记录 + 闪烁 */
  useEffect(() => {
    if (recordJump === null) return;
    const el = document.querySelector<HTMLElement>(`[data-record-index="${recordJump.index}"]`);
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
    setFlashIdx(recordJump.index);
    setOpenIdx(recordJump.index);
    const t = setTimeout(() => setFlashIdx(null), 1800);
    return () => clearTimeout(t);
  }, [recordJump]);

  /** 打开浮层（锚定触发按钮中心/底部） */
  const openPopover = (target: AnnotationTarget, e: React.MouseEvent<HTMLElement>) => {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setPopover({ target, anchor: { x: r.left + r.width / 2, y: r.bottom } });
    setNote("");
  };

  const closePopover = () => {
    setPopover(null);
    setNote("");
  };

  const savePopover = () => {
    if (!popover) return;
    void onSaveAnnotation(popover.target, note.trim());
    closePopover();
  };

  return (
    <div className="results-section">
      <div className="results-header">
        <span>抽取结果（{records.length} 条记录）</span>
        <span className="mono text-2">悬停行或字段可添加批注（不影响原结果）</span>
      </div>
      {records.length === 0 && (
        <div className="results-empty">运行「③ 主抽取」后显示结果。</div>
      )}
      {records.length > 0 && (
        <div className="results-table-wrap">
          <table className="results-table">
            <thead>
              <tr>
                <th className="row-num">#</th>
                {COLUMNS.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {records.map((r, i) => {
                const rowAnnos = annotations.filter((a) => a.record_index === i);
                return (
                  <RowBlock
                    key={i}
                    index={i}
                    record={r}
                    rowAnnos={rowAnnos}
                    open={openIdx === i}
                    onToggle={() => setOpenIdx(openIdx === i ? null : i)}
                    onAnnotate={openPopover}
                    flash={flashIdx === i}
                  />
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {popover && (
        <AnnotationPopover
          target={popover.target}
          anchor={popover.anchor}
          note={note}
          onNoteChange={setNote}
          onSave={savePopover}
          onCancel={closePopover}
        />
      )}
    </div>
  );
}

function RowBlock({
  index,
  record,
  rowAnnos,
  open,
  onToggle,
  onAnnotate,
  flash,
}: {
  index: number;
  record: ExtractRecord;
  rowAnnos: Annotation[];
  open: boolean;
  onToggle: () => void;
  onAnnotate: (t: AnnotationTarget, e: React.MouseEvent<HTMLElement>) => void;
  flash: boolean;
}) {
  const hasAnno = rowAnnos.length > 0;
  return (
    <>
      <tr
        className={`results-row${hasAnno ? " has-annotation" : ""}${flash ? " flash" : ""}`}
        data-record-index={index}
        onClick={onToggle}
      >
        <td className="row-num">
          <span className="row-index">{index + 1}</span>
          {hasAnno && <span className="anno-dot" title={`${rowAnnos.length} 条批注`} />}
          <button
            className="btn btn-sm anno-add"
            onClick={(e) => {
              e.stopPropagation();
              onAnnotate({ record_index: index }, e);
            }}
            title="为这条记录添加批注"
          >
            ＋批注
          </button>
        </td>
        {COLUMNS.map((c) => (
          <td key={c}>{cellText(record[c])}</td>
        ))}
      </tr>
      {open && (
        <tr className="results-detail-row">
          <td colSpan={COLUMNS.length + 1}>
            <RecordDetail record={record} index={index} onAnnotate={onAnnotate} />
          </td>
        </tr>
      )}
    </>
  );
}

/* 字段级批注入口：值旁小旗标（hover 显示） */
function AnnotatableValue({
  label,
  value,
  onAnnotate,
}: {
  label: string;
  value: unknown;
  onAnnotate: (e: React.MouseEvent<HTMLElement>) => void;
}) {
  const text = cellText(value);
  return (
    <span className="annotatable-value">
      <span className="mini-k mono">{label}:</span> {text}
      <button
        className="btn btn-sm flag-btn"
        onClick={(e) => {
          e.stopPropagation();
          onAnnotate(e);
        }}
        title={`为字段「${label}」添加批注`}
      >
        ⚑
      </button>
    </span>
  );
}

function RecordDetail({
  record,
  index,
  onAnnotate,
}: {
  record: ExtractRecord;
  index: number;
  onAnnotate: (t: AnnotationTarget, e: React.MouseEvent<HTMLElement>) => void;
}) {
  const structuredTables: Array<[string, Array<Record<string, unknown>>]> = [
    ["合成温度_结构化", record["合成温度_结构化"] as Array<Record<string, unknown>>],
    ["比表面积_结构化", record["比表面积_结构化"] as Array<Record<string, unknown>>],
    ["孔径_结构化", record["孔径_结构化"] as Array<Record<string, unknown>>],
  ].filter(([, v]) => Array.isArray(v) && v.length > 0) as Array<
    [string, Array<Record<string, unknown>>]
  >;

  return (
    <div className="record-detail">
      <div className="detail-subtitle">关键字段（可逐字段批注）</div>
      <div className="detail-fields">
        {COLUMNS.map((c) => (
          <div key={c} className="detail-field">
            <AnnotatableValue
              label={c}
              value={record[c]}
              onAnnotate={(e) =>
                onAnnotate(
                  {
                    record_index: index,
                    field: c,
                    value_snapshot: String(record[c] ?? "00").slice(0, 120),
                  },
                  e,
                )
              }
            />
          </div>
        ))}
      </div>

      {structuredTables.length > 0 && (
        <div className="detail-structured">
          {structuredTables.map(([title, rows]) => (
            <div key={title}>
              <div className="detail-subtitle">{title}</div>
              <table className="mini-table">
                <tbody>
                  {rows.map((row, i) => (
                    <tr key={i}>
                      {Object.entries(row).map(([k, v]) => (
                        <td key={k}>
                          <AnnotatableValue
                            label={k}
                            value={v}
                            onAnnotate={(e) =>
                              onAnnotate(
                                {
                                  record_index: index,
                                  field: `${title}.${k}`,
                                  value_snapshot: String(v ?? "00").slice(0, 120),
                                },
                                e,
                              )
                            }
                          />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}

      {record["字段引用"] && (
        <div className="detail-citations">
          <div className="detail-subtitle">字段引用</div>
          {Object.entries(record["字段引用"]).map(([field, sentences]) => (
            <div key={field} className="citation-item">
              <span className="citation-field">{field}</span>
              <ul>
                {(sentences as string[]).map((s, i) => (
                  <li key={i} className="mono">
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      <div className="detail-subtitle">完整记录</div>
      <pre className="record-json mono">
        {JSON.stringify(record, null, 2).replace(/^\{|\}$/g, "")}
      </pre>
    </div>
  );
}
