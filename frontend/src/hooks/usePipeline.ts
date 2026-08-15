/* usePipeline.ts — 5 步流水线状态机：①解析 → ②路由 → ③抽取 → ④引用 → ⑤结构化 */
import { useCallback, useEffect, useReducer } from "react";
import type {
  ExtractRecord,
  ParseStepData,
  PipelineStep,
  RoutingResult,
  StepId,
} from "../types";
import {
  errText,
  runCite,
  runExtract,
  runParse,
  runRoute,
  runStructurize,
} from "../api/client";

const STEP_DEFS: Array<Omit<PipelineStep, "status">> = [
  { id: "parse", label: "① PDF 解析", description: "版面重建 → markdown（本地计算）" },
  { id: "route", label: "② 路由分类", description: "软模板 / 复合结构 / 硬模板" },
  { id: "extract", label: "③ 主抽取", description: "结构化实验记录" },
  { id: "cite", label: "④ 字段引用", description: "字段级整句原文回标" },
  { id: "structurize", label: "⑤ 数值结构化", description: "机器可读数值字段" },
];

interface State {
  steps: PipelineStep[];
  /** 当前累积的抽取记录（extract/cite/structurize 逐步更新） */
  records: ExtractRecord[];
}

type Action =
  | { type: "start"; id: StepId }
  | { type: "done"; id: StepId; payload: unknown; tookMs?: number; warning?: string }
  | { type: "skip"; id: StepId; reason: string }
  | { type: "fail"; id: StepId; error: string }
  | { type: "records"; records: ExtractRecord[] }
  | { type: "reset" };

function initialState(): State {
  return {
    steps: STEP_DEFS.map((s) => ({ ...s, status: "pending" })),
    records: [],
  };
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "start":
      return {
        ...state,
        steps: state.steps.map((s) =>
          s.id === action.id ? { ...s, status: "running", error: undefined } : s,
        ),
      };
    case "done":
      return {
        ...state,
        steps: state.steps.map((s) =>
          s.id === action.id
            ? {
                ...s,
                status: "done",
                payload: action.payload,
                took_ms: action.tookMs,
                warning: action.warning,
                error: undefined,
              }
            : s,
        ),
      };
    case "skip":
      return {
        ...state,
        steps: state.steps.map((s) =>
          s.id === action.id
            ? { ...s, status: "done", skipped: true, payload: { reason: action.reason } }
            : s,
        ),
      };
    case "fail":
      return {
        ...state,
        steps: state.steps.map((s) =>
          s.id === action.id ? { ...s, status: "error", error: action.error } : s,
        ),
      };
    case "records":
      return { ...state, records: action.records };
    case "reset":
      return initialState();
    default:
      return state;
  }
}

export interface UsePipelineOptions {
  paperId: string | null;
  /** 论文文本（无 PDF 的 corpus 论文从 /text 加载） */
  text: string;
  /** 论文是否有原始 PDF（决定 parse 步骤可执行性） */
  hasPdf: boolean;
}

export function usePipeline({ paperId, text, hasPdf }: UsePipelineOptions) {
  const [state, dispatch] = useReducer(reducer, undefined, initialState);

  // corpus 论文（无原始 PDF）：解析步骤自动置为跳过态，解锁后续步骤
  useEffect(() => {
    if (paperId && !hasPdf) {
      dispatch({
        type: "skip",
        id: "parse",
        reason: "该论文为语料库既有解析文本（无原始 PDF），跳过版面重建。",
      });
    }
  }, [paperId, hasPdf]);

  const isStepReady = useCallback(
    (id: StepId): boolean => {
      if (!paperId) return false;
      const idx = STEP_DEFS.findIndex((s) => s.id === id);
      if (idx === 0) return hasPdf;
      const prev = state.steps[idx - 1];
      return prev.status === "done";
    },
    [paperId, hasPdf, state.steps],
  );

  /** 步骤是否可以手动重跑（已 done/error 且输入就绪） */
  const canRerun = useCallback(
    (id: StepId): boolean => {
      if (!paperId) return false;
      const idx = STEP_DEFS.findIndex((s) => s.id === id);
      if (idx === 0) return hasPdf;
      return state.steps[idx - 1].status === "done";
    },
    [paperId, hasPdf, state.steps],
  );

  const runStep = useCallback(
    async (id: StepId) => {
      if (!paperId) return;
      if (!isStepReady(id)) return;
      dispatch({ type: "start", id });
      try {
        if (id === "parse") {
          const r = await runParse(paperId);
          const data = r.data as ParseStepData;
          if (data.skipped) {
            dispatch({ type: "skip", id, reason: data.reason ?? "无原始 PDF，跳过解析。" });
          } else {
            dispatch({ type: "done", id, payload: data, tookMs: r.took_ms });
          }
        } else if (id === "route") {
          const r = await runRoute(text);
          dispatch({ type: "done", id, payload: r.data, tookMs: r.took_ms });
        } else if (id === "extract") {
          const routing = state.steps[1].payload as RoutingResult;
          const r = await runExtract(text, routing);
          dispatch({ type: "records", records: r.data });
          dispatch({ type: "done", id, payload: r.data, tookMs: r.took_ms, warning: r.warning });
        } else if (id === "cite") {
          const r = await runCite(text, state.records);
          dispatch({ type: "records", records: r.data });
          dispatch({ type: "done", id, payload: r.data, tookMs: r.took_ms });
        } else if (id === "structurize") {
          const r = await runStructurize(state.records);
          dispatch({ type: "records", records: r.data });
          dispatch({ type: "done", id, payload: r.data, tookMs: r.took_ms });
        }
      } catch (e) {
        dispatch({ type: "fail", id, error: errText(e) });
      }
    },
    [paperId, text, state.steps, state.records, isStepReady],
  );

  /** 顺序执行所有就绪步骤，遇错即停 */
  const runAll = useCallback(async () => {
    for (const s of state.steps) {
      if (s.status === "done") continue;
      if (s.id === "parse" && !hasPdf) continue;
      await runStep(s.id);
      const current = state.steps.find((x) => x.id === s.id);
      if (current?.status === "error") break;
    }
  }, [state.steps, hasPdf, runStep]);

  const reset = useCallback(() => dispatch({ type: "reset" }), []);

  return {
    steps: state.steps,
    records: state.records,
    runStep,
    runAll,
    reset,
    isStepReady,
    canRerun,
  };
}
