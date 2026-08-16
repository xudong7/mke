/* api/client.ts — axios 实例与类型化端点封装 */
import axios, { AxiosError } from "axios";
import type {
  Annotation,
  HealthInfo,
  Paper,
  ParseStepData,
  RoutingResult,
  StepResult,
  ExtractRecord,
} from "../types";

// 普通调用 30s；流水线 LLM 步骤可能耗时更长（见各端点单独配置）
const api = axios.create({ baseURL: "/api", timeout: 30_000 });

const pipelineApi = axios.create({ baseURL: "/api", timeout: 300_000 });

/** 抽取 axios 错误的可读信息 */
export function errText(e: unknown): string {
  if (axios.isAxiosError(e)) {
    const ax = e as AxiosError<{ detail?: string }>;
    if (ax.response?.data?.detail) return ax.response.data.detail;
    if (ax.code === "ECONNABORTED") return "请求超时（后端处理过慢）";
    return `${ax.message}${ax.response ? ` (HTTP ${ax.response.status})` : ""}`;
  }
  return String(e);
}

/* ---- 健康检查 ---- */
export async function fetchHealth(): Promise<HealthInfo> {
  const { data } = await api.get<HealthInfo>("/health");
  return data;
}

/* ---- 论文 ---- */
export async function fetchPapers(): Promise<Paper[]> {
  const { data } = await api.get<Paper[]>("/papers");
  return data;
}

export async function fetchPaperText(paperId: string): Promise<string> {
  const { data } = await api.get<{ paper_id: string; text: string }>(
    `/papers/${encodeURIComponent(paperId)}/text`,
  );
  return data.text;
}

export function pdfUrl(paperId: string): string {
  return `/api/papers/${encodeURIComponent(paperId)}/pdf`;
}

export async function uploadPdf(file: File): Promise<{
  paper_id: string;
  has_pdf: boolean;
  text_size: number;
  warnings: string[];
}> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post("/papers/upload", form, {
    timeout: 60_000,
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

/* ---- 流水线（5 步） ---- */
export async function runParse(paperId: string): Promise<StepResult<ParseStepData>> {
  const { data } = await pipelineApi.post<StepResult<ParseStepData>>("/pipeline/parse", {
    paper_id: paperId,
  });
  return data;
}

export async function runRoute(text: string): Promise<StepResult<RoutingResult>> {
  const { data } = await pipelineApi.post<StepResult<RoutingResult>>("/pipeline/route", { text });
  return data;
}

export async function runExtract(
  text: string,
  routing: RoutingResult,
): Promise<StepResult<ExtractRecord[]>> {
  const { data } = await pipelineApi.post<StepResult<ExtractRecord[]>>("/pipeline/extract", {
    text,
    routing,
  });
  return data;
}

export async function runCite(
  text: string,
  results: ExtractRecord[],
): Promise<StepResult<ExtractRecord[]>> {
  const { data } = await pipelineApi.post<StepResult<ExtractRecord[]>>("/pipeline/cite", {
    text,
    results,
  });
  return data;
}

export async function runStructurize(
  results: ExtractRecord[],
): Promise<StepResult<ExtractRecord[]>> {
  const { data } = await pipelineApi.post<StepResult<ExtractRecord[]>>(
    "/pipeline/structurize",
    { results },
    { timeout: 600_000 },
  );
  return data;
}

/* ---- 批注 ---- */
export async function fetchAnnotations(paperId: string): Promise<Annotation[]> {
  const { data } = await api.get<Annotation[]>(
    `/papers/${encodeURIComponent(paperId)}/annotations`,
  );
  return data;
}

export async function createAnnotation(
  paperId: string,
  body: { page: number | null; quote: string; note: string; anchor: Annotation["anchor"] },
): Promise<Annotation> {
  const { data } = await api.post<Annotation>(
    `/papers/${encodeURIComponent(paperId)}/annotations`,
    body,
  );
  return data;
}

export async function deleteAnnotation(annotationId: string): Promise<void> {
  await api.delete(`/annotations/${annotationId}`);
}
