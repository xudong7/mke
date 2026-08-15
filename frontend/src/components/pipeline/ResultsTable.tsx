/* ResultsTable.tsx — 最终抽取结果表：关键列 + 可展开完整记录（字段引用 / *_结构化 渲染） */
import { useState } from "react";
import type { ExtractRecord } from "../../types";

const COLUMNS: Array<keyof ExtractRecord> = [
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

function cellText(v: unknown): string {
  if (v == null) return "00";
  return String(v).slice(0, 120);
}

export function ResultsTable({ records }: { records: ExtractRecord[] }) {
  const [openIdx, setOpenIdx] = useState<number | null>(null);

  return (
    <div className="results-section">
      <div className="results-header">
        <span>抽取结果（{records.length} 条记录）</span>
        <span className="mono text-2">点击行展开完整字段</span>
      </div>
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
            {records.map((r, i) => (
              <RowExpander
                key={i}
                index={i}
                record={r}
                open={openIdx === i}
                onToggle={() => setOpenIdx(openIdx === i ? null : i)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RowExpander({
  index,
  record,
  open,
  onToggle,
}: {
  index: number;
  record: ExtractRecord;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr className="results-row" onClick={onToggle}>
        <td className="row-num mono">{index + 1}</td>
        {COLUMNS.map((c) => (
          <td key={c}>{cellText(record[c])}</td>
        ))}
      </tr>
      {open && (
        <tr className="results-detail-row">
          <td colSpan={COLUMNS.length + 1}>
            <RecordDetail record={record} />
          </td>
        </tr>
      )}
    </>
  );
}

function RecordDetail({ record }: { record: ExtractRecord }) {
  const structuredTables: Array<[string, Array<Record<string, unknown>>]> = [
    ["合成温度_结构化", record["合成温度_结构化"] as Array<Record<string, unknown>>],
    ["比表面积_结构化", record["比表面积_结构化"] as Array<Record<string, unknown>>],
    ["孔径_结构化", record["孔径_结构化"] as Array<Record<string, unknown>>],
  ].filter(([, v]) => Array.isArray(v) && v.length > 0) as Array<
    [string, Array<Record<string, unknown>>]
  >;

  return (
    <div className="record-detail">
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
                          <span className="mini-k mono">{k}:</span> {cellText(v)}
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
