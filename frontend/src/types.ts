/* types.ts — 与后端 API 对齐的类型定义 */

export interface Paper {
  id: string;
  source: "corpus" | "upload";
  title: string;
  first_author: string;
  year: string;
  text_size: number;
  has_pdf: boolean;
}

export interface HealthInfo {
  ok: boolean;
  model: string;
  base_url: string;
  llm_configured: boolean;
}

/* ---- 流水线 ---- */

export type AnalysisType = "soft_template_full" | "core_shell_simple" | "hard_template_simple";

export interface RoutingResult {
  analysis_type: AnalysisType;
  selected_skills: string[];
  reason_zh: string;
  source_snippets: string[];
}

export interface ParseStepData {
  skipped?: boolean;
  reason?: string;
  pages?: Array<{
    page: number;
    columns: number;
    filtered: Array<[string, string]>;
    blocks_kept: number;
  }>;
  column_stats?: { single: number; double: number };
  header_footer_filtered_count?: number;
  section_count?: number;
  markdown: string;
  meta: {
    page_count?: number;
    char_count?: number;
    body_size_pt?: number;
    header_texts?: string[];
  };
}

export interface StepResult<T> {
  data: T;
  took_ms: number;
  warning?: string;
}

/* ---- 抽取记录 ---- */

/** 结果批注：挂 (run, record_index, 可选字段)，不影响原结果 */
export interface Annotation {
  id: string;
  run_id: string;
  paper_id: string;
  record_index: number;
  field?: string | null;
  note: string;
  value_snapshot?: string | null;
  created_at: string;
}

/** 抽取记录：18 个基础字段 + 引用/结构化扩展（中文属性名用字符串字面量形式声明） */
export interface ExtractRecord {
  "来源文件"?: string;
  "分析类型"?: string;
  "组装方式"?: string;
  "溶剂体系"?: string;
  "pH值_酸碱浓度"?: string;
  "表面活性剂种类"?: string;
  "表面活性剂浓度"?: string;
  "硅/钛源种类_浓度"?: string;
  "盐种类_浓度"?: string;
  "合成温度"?: string;
  "介孔结构"?: string;
  "比表面积"?: string;
  "孔径"?: string;
  "产物形态"?: string;
  "其他变量"?: string;
  "来源文本片段"?: string;
  "推理说明"?: string;
  "字段引用"?: Record<string, string[]>;
  "合成温度_结构化"?: Array<Record<string, unknown>>;
  "比表面积_结构化"?: Array<Record<string, unknown>>;
  "孔径_结构化"?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

/* ---- 流水线步骤 ---- */

export type StepId = "parse" | "route" | "extract" | "cite" | "structurize";
export type StepStatus = "pending" | "running" | "done" | "error";
export type RunStatus = "running" | "done" | "failed";

export interface PipelineStep {
  id: StepId;
  label: string;
  description: string;
  status: StepStatus;
  payload?: unknown;
  error?: string;
  took_ms?: number;
  warning?: string;
  /** parse 步骤对 corpus 论文自动跳过 */
  skipped?: boolean;
}

/* ---- 运行历史 ---- */

export interface RunStepState {
  status: StepStatus;
  payload?: unknown;
  took_ms?: number | null;
  warning?: string | null;
}

export interface RunSummary {
  id: string;
  paper_id: string;
  created_at: string;
  updated_at: string;
  status: RunStatus;
  record_count: number;
  step_statuses: Record<StepId, StepStatus>;
}

export interface RunDetail extends RunSummary {
  steps: Record<StepId, RunStepState>;
  records: ExtractRecord[];
}
