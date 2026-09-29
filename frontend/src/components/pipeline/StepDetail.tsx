/* StepDetail.tsx — 按步骤类型定制的中间结果渲染（可切换查看原始 JSON） */
import { useState } from "react";
import type {
  ExtractRecord,
  ParseStepData,
  PipelineStep,
  RoutingResult,
} from "../../types";

const ANALYSIS_LABELS: Record<string, string> = {
  soft_template_full: "软模板法 · 完整分析",
  core_shell_simple: "复合结构 · 简单分析",
  hard_template_simple: "自模板/硬模板 · 简单分析",
};

/* ---- 防御性类型收窄（历史加载的部分 payload 也能渲染） ---- */
function asParse(p: unknown): ParseStepData {
  return (p ?? {}) as ParseStepData;
}
function asRoute(p: unknown): RoutingResult {
  return (p ?? {}) as RoutingResult;
}
function asRecords(p: unknown): ExtractRecord[] {
  return Array.isArray(p) ? (p as ExtractRecord[]) : [];
}

export function StepDetail({ step }: { step: PipelineStep }) {
  const [rawOpen, setRawOpen] = useState(false);
  if (step.payload === undefined || step.payload === null) return null;

  return (
    <div className="step-detail">
      {step.id === "parse" && <ParseDetail payload={step.payload} />}
      {step.id === "route" && <RouteDetail payload={step.payload} />}
      {step.id === "extract" && <ExtractDetail payload={step.payload} />}
      {step.id === "cite" && <CiteDetail payload={step.payload} />}
      {step.id === "structurize" && <StructurizeDetail payload={step.payload} />}

      <button
        className="step-raw-toggle mono"
        onClick={() => setRawOpen((v) => !v)}
      >
        {rawOpen ? "收起" : "查看"}原始 JSON
      </button>
      {rawOpen && (
        <div className="step-payload mono">
          <pre>{JSON.stringify(step.payload, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

/* ---- ① 解析：版面统计 + markdown 预览 + 过滤清单 ---- */
function ParseDetail({ payload }: { payload: unknown }) {
  const p = asParse(payload);
  const meta = p.meta ?? {};
  const stats: Array<[string, number]> = [
    ["页数", meta.page_count ?? 0],
    ["单栏", p.column_stats?.single ?? 0],
    ["双栏", p.column_stats?.double ?? 0],
    ["过滤页眉页脚", p.header_footer_filtered_count ?? 0],
    ["章节数", p.section_count ?? 0],
    ["字符数", meta.char_count ?? 0],
  ];
  const filteredItems = (p.pages ?? [])
    .flatMap((pg) =>
      (pg.filtered ?? []).map(([kind, t]) => ({ page: pg.page, kind, t })),
    )
    .slice(0, 8);

  return (
    <>
      <div className="stat-cards">
        {stats.map(([k, v]) => (
          <div key={k} className="stat-card">
            <div className="v mono">{v}</div>
            <div className="k">{k}</div>
          </div>
        ))}
      </div>
      {p.markdown && (
        <>
          <div className="step-subtitle">解析结果（markdown）</div>
          <div className="step-markdown mono">
            <pre>{p.markdown}</pre>
          </div>
        </>
      )}
      {filteredItems.length > 0 && (
        <>
          <div className="step-subtitle">过滤的页眉页脚（前 {filteredItems.length} 条）</div>
          <div className="step-filtered mono">
            {filteredItems.map((f, i) => (
              <div key={i}>
                <span className="filtered-kind">{f.kind}</span> 第 {f.page} 页 — {f.t.slice(0, 60)}
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}

/* ---- ② 路由：分类徽标 + 推理 + skills + 原文片段 ---- */
function RouteDetail({ payload }: { payload: unknown }) {
  const r = asRoute(payload);
  return (
    <>
      <div className="analysis-badge">
        {ANALYSIS_LABELS[r.analysis_type] ?? r.analysis_type ?? "未知"}
      </div>
      {r.reason_zh && (
        <>
          <div className="step-subtitle">路由判断</div>
          <div className="route-reason">{r.reason_zh}</div>
        </>
      )}
      {r.selected_skills && r.selected_skills.length > 0 && (
        <>
          <div className="step-subtitle">使用技能模块</div>
          <div className="skill-chips">
            {r.selected_skills.map((s) => (
              <span key={s} className="skill-chip mono">
                {s}
              </span>
            ))}
          </div>
        </>
      )}
      {r.source_snippets && r.source_snippets.length > 0 && (
        <>
          <div className="step-subtitle">关键原文依据</div>
          <div className="route-snippets">
            {r.source_snippets.map((s, i) => (
              <blockquote key={i} className="mono">
                {s}
              </blockquote>
            ))}
          </div>
        </>
      )}
    </>
  );
}

/* ---- ③ 主抽取：记录数摘要 + 跳转结果表 ---- */
function ExtractDetail({ payload }: { payload: unknown }) {
  const records = asRecords(payload);
  const types = [...new Set(records.map((r) => r["分析类型"]).filter(Boolean))] as string[];
  return (
    <>
      <div className="step-summary">
        共 <b>{records.length}</b> 条记录
        {types.length > 0 && (
          <span className="skill-chips" style={{ marginLeft: 8 }}>
            {types.map((t) => (
              <span key={t} className="skill-chip">
                {t}
              </span>
            ))}
          </span>
        )}
        <button
          className="btn btn-sm"
          style={{ marginLeft: 8 }}
          onClick={() =>
            document.querySelector(".results-section")?.scrollIntoView({
              behavior: "smooth",
              block: "start",
            })
          }
        >
          查看结果表 ↓
        </button>
      </div>
    </>
  );
}

/* ---- ④ 字段引用：汇总 + 每条记录 details ---- */
function CiteDetail({ payload }: { payload: unknown }) {
  const records = asRecords(payload);
  let fieldCount = 0;
  let sentenceCount = 0;
  const perRecord = records.map((r, i) => {
    const cites = (r["字段引用"] ?? {}) as Record<string, string[]>;
    const fields = Object.entries(cites).filter(([, v]) => Array.isArray(v) && v.length > 0);
    const sentences = fields.reduce((n, [, v]) => n + v.length, 0);
    fieldCount += fields.length;
    sentenceCount += sentences;
    return { index: i, fields, sentences };
  });
  return (
    <>
      <div className="step-summary">
        共 <b>{records.length}</b> 条记录 · <b>{fieldCount}</b> 个字段 ·{" "}
        <b>{sentenceCount}</b> 句原文引用
      </div>
      {perRecord.map((pr) => (
        <details key={pr.index} className="cite-record">
          <summary className="mono">
            记录 #{pr.index + 1}: {pr.fields.length} 个字段 · {pr.sentences} 句引用
          </summary>
          <div className="detail-citations">
            {pr.fields.map(([field, sentences]) => (
              <div key={field} className="citation-item">
                <span className="citation-field">{field}</span>
                <ul>
                  {sentences.map((s, i) => (
                    <li key={i} className="mono">
                      {s}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </details>
      ))}
    </>
  );
}

/* ---- ⑤ 数值结构化：三类字段统计 ---- */
function StructurizeDetail({ payload }: { payload: unknown }) {
  const records = asRecords(payload);
  const count = (k: string) =>
    records.filter((r) => Array.isArray(r[k]) && (r[k] as unknown[]).length > 0).length;
  const chips: Array<[string, string, number]> = [
    ["合成温度_结构化", "温度", count("合成温度_结构化")],
    ["比表面积_结构化", "比表面积", count("比表面积_结构化")],
    ["孔径_结构化", "孔径", count("孔径_结构化")],
  ];
  return (
    <>
      <div className="step-summary">
        共 <b>{records.length}</b> 条记录
      </div>
      <div className="struct-chips">
        {chips.map(([k, label, n]) => (
          <span key={k} className={`struct-chip${n > 0 ? " has" : ""}`}>
            {label} <b>{n}</b> 条
          </span>
        ))}
      </div>
    </>
  );
}
