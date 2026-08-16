/* usePipeline.ts — 5 步流水线状态机 + 运行历史同步
 *
 * 关键设计：
 * - executeStep 是【无就绪门控】的内部执行器，跨步输入（routing/records）
 *   从参数链式传入，绝不读闭包 state —— 这是 runAll 能顺序跑完全部步骤的前提
 *   （v1 bug：runAll 闭包捕获旧 state，isStepReady 对后续步骤恒 false）
 * - 每个步骤完成后 fire-and-forget 同步到后端 run（绝不因同步失败中断流水线）
 * - loadRun 从历史完整恢复看板状态，可继续运行或重新运行
 */
import { useCallback, useEffect, useReducer, useRef } from "react";
import type {
  ExtractRecord,
  ParseStepData,
  PipelineStep,
  RoutingResult,
  RunDetail,
  RunStatus,
  StepId,
} from "../types";
import {
  createRun,
  errText,
  runCite,
  runExtract,
  runParse,
  runRoute,
  runStructurize,
  updateRunStep,
} from "../api/client";

const STEP_DEFS: Array<Omit<PipelineStep, "status">> = [
  { id: "parse", label: "① PDF 解析", description: "版面重建 → markdown（本地计算）" },
  { id: "route", label: "② 路由分类", description: "软模板 / 复合结构 / 硬模板" },
  { id: "extract", label: "③ 主抽取", description: "结构化实验记录" },
  { id: "cite", label: "④ 字段引用", description: "字段级整句原文回标" },
  { id: "structurize", label: "⑤ 数值结构化", description: "机器可读数值字段" },
];

interface State {
  runId: string | null;
  steps: PipelineStep[];
  /** 当前累积的抽取记录（extract/cite/structurize 逐步更新） */
  records: ExtractRecord[];
}

type Action =
  | { type: "runCreated"; runId: string }
  | { type: "start"; id: StepId }
  | { type: "done"; id: StepId; payload: unknown; tookMs?: number; warning?: string }
  | { type: "skip"; id: StepId; reason: string }
  | { type: "fail"; id: StepId; error: string }
  | { type: "records"; records: ExtractRecord[] }
  | { type: "loadRun"; run: RunDetail }
  | { type: "reset" };

function initialState(): State {
  return {
    runId: null,
    steps: STEP_DEFS.map((s) => ({ ...s, status: "pending" })),
    records: [],
  };
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "runCreated":
      return { ...state, runId: action.runId };
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
    case "loadRun": {
      const stepMap = action.run.steps;
      return {
        runId: action.run.id,
        records: action.run.records,
        steps: STEP_DEFS.map((s) => {
          const rs = stepMap[s.id];
          const status =
            rs.status === "error" ? "error" : rs.status === "done" ? "done" : "pending";
          return {
            ...s,
            status,
            payload: rs.payload ?? undefined,
            took_ms: rs.took_ms ?? undefined,
            warning: rs.warning ?? undefined,
            skipped: s.id === "parse" && rs.status === "done" && rs.payload === null,
          };
        }),
      };
    }
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

/** 步骤执行输入（从调用方链式传入，不读闭包 state） */
interface StepInputs {
  routing?: RoutingResult;
  records?: ExtractRecord[];
}

export function usePipeline({ paperId, text, hasPdf }: UsePipelineOptions) {
  const [state, dispatch] = useReducer(reducer, undefined, initialState);

  // state 镜像：仅用于 UI 门控与状态派生读取（不参与执行链）
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  // 防双创建：快速连点两次"运行"不能创建两个 run
  const runCreatePromiseRef = useRef<Promise<string> | null>(null);

  const ensureRun = useCallback(async (): Promise<string> => {
    if (stateRef.current.runId) return stateRef.current.runId;
    if (runCreatePromiseRef.current) return runCreatePromiseRef.current;
    const p = (async () => {
      const run = await createRun(paperId!);
      dispatch({ type: "runCreated", runId: run.id });
      return run.id;
    })();
    runCreatePromiseRef.current = p;
    try {
      return await p;
    } finally {
      runCreatePromiseRef.current = null;
    }
  }, [paperId]);

  /** 执行单步：无就绪门控；成功/失败后同步到后端 run */
  const executeStep = useCallback(
    async (id: StepId, inputs: StepInputs): Promise<{ ok: boolean; payload?: unknown }> => {
      if (!paperId) return { ok: false };
      let runId: string;
      try {
        runId = await ensureRun();
      } catch (e) {
        dispatch({ type: "fail", id, error: `创建运行记录失败：${errText(e)}` });
        return { ok: false };
      }

      dispatch({ type: "start", id });
      const sync = (status: Parameters<typeof updateRunStep>[2]["status"], extra: Record<string, unknown> = {}) => {
        void updateRunStep(runId, id, { status, ...extra }).catch((e) =>
          console.warn("run 同步失败（不影响流水线）:", e),
        );
      };

      try {
        if (id === "parse") {
          const r = await runParse(paperId);
          const data = r.data as ParseStepData;
          if (data.skipped) {
            dispatch({ type: "skip", id, reason: data.reason ?? "无原始 PDF，跳过解析。" });
            sync("done", { took_ms: r.took_ms });
          } else {
            dispatch({ type: "done", id, payload: data, tookMs: r.took_ms });
            sync("done", { payload: data, took_ms: r.took_ms });
          }
          return { ok: true, payload: data };
        }
        if (id === "route") {
          const r = await runRoute(text);
          dispatch({ type: "done", id, payload: r.data, tookMs: r.took_ms });
          sync("done", { payload: r.data, took_ms: r.took_ms });
          return { ok: true, payload: r.data };
        }
        if (id === "extract") {
          const r = await runExtract(text, inputs.routing!);
          dispatch({ type: "records", records: r.data });
          dispatch({ type: "done", id, payload: r.data, tookMs: r.took_ms, warning: r.warning });
          sync("done", { payload: r.data, took_ms: r.took_ms, warning: r.warning });
          return { ok: true, payload: r.data };
        }
        if (id === "cite") {
          const r = await runCite(text, inputs.records ?? []);
          dispatch({ type: "records", records: r.data });
          dispatch({ type: "done", id, payload: r.data, tookMs: r.took_ms });
          sync("done", { payload: r.data, took_ms: r.took_ms });
          return { ok: true, payload: r.data };
        }
        if (id === "structurize") {
          const r = await runStructurize(inputs.records ?? []);
          dispatch({ type: "records", records: r.data });
          dispatch({ type: "done", id, payload: r.data, tookMs: r.took_ms });
          sync("done", { payload: r.data, took_ms: r.took_ms });
          return { ok: true, payload: r.data };
        }
        return { ok: false };
      } catch (e) {
        const msg = errText(e);
        dispatch({ type: "fail", id, error: msg });
        sync("error");
        return { ok: false };
      }
    },
    [paperId, text, ensureRun],
  );

  const isStepReady = useCallback(
    (id: StepId): boolean => {
      if (!paperId) return false;
      const idx = STEP_DEFS.findIndex((s) => s.id === id);
      if (idx === 0) return hasPdf;
      return stateRef.current.steps[idx - 1].status === "done";
    },
    [paperId, hasPdf],
  );

  const canRerun = useCallback(
    (id: StepId): boolean => {
      if (!paperId) return false;
      const idx = STEP_DEFS.findIndex((s) => s.id === id);
      if (idx === 0) return hasPdf;
      return stateRef.current.steps[idx - 1].status === "done";
    },
    [paperId, hasPdf],
  );

  /** 公开单步执行：保留就绪门控 */
  const runStep = useCallback(
    async (id: StepId) => {
      if (!isStepReady(id)) return;
      const cur = stateRef.current.steps.find((s) => s.id === id);
      const inputs: StepInputs = {};
      if (id === "extract") inputs.routing = stateRef.current.steps[1].payload as RoutingResult;
      if (id === "cite" || id === "structurize") inputs.records = stateRef.current.records;
      void cur; // 占位保持语义清晰
      await executeStep(id, inputs);
    },
    [isStepReady, executeStep],
  );

  /** 顺序执行全部步骤（修复 v1 闭包 bug）：本地变量链式传递，不检查状态 */
  const runAll = useCallback(
    async (options?: { fresh?: boolean }) => {
      const fresh = options?.fresh ?? false;
      let routing: RoutingResult | undefined;
      let records: ExtractRecord[] = fresh ? [] : stateRef.current.records;

      for (const def of STEP_DEFS) {
        // 非 fresh 模式：已完成的步骤跳过（种子数据来自其 payload）
        if (!fresh) {
          const cur = stateRef.current.steps.find((s) => s.id === def.id);
          if (cur?.status === "done") {
            if (def.id === "route") routing = cur.payload as RoutingResult;
            if (def.id === "extract" || def.id === "cite" || def.id === "structurize") {
              records = (cur.payload as ExtractRecord[]) ?? records;
            }
            continue;
          }
        }
        if (def.id === "parse" && !hasPdf) continue;

        const out = await executeStep(def.id, { routing, records });
        if (!out.ok) break;
        if (def.id === "route") routing = out.payload as RoutingResult;
        if (def.id === "extract" || def.id === "cite" || def.id === "structurize") {
          records = (out.payload as ExtractRecord[]) ?? records;
        }
      }
    },
    [hasPdf, executeStep],
  );

  /** 从历史加载完整 run 到看板（零 LLM 调用） */
  const loadRun = useCallback((run: RunDetail) => {
    dispatch({ type: "loadRun", run });
  }, []);

  const reset = useCallback(() => dispatch({ type: "reset" }), []);

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

  const runStatus: RunStatus | null = (() => {
    const statuses = state.steps.map((s) => s.status);
    if (statuses.includes("error")) return "failed";
    if (statuses.includes("running")) return "running";
    if (statuses.every((s) => s === "done")) return "done";
    return null;
  })();

  return {
    steps: state.steps,
    records: state.records,
    runId: state.runId,
    runStatus,
    runStep,
    runAll,
    loadRun,
    reset,
    isStepReady,
    canRerun,
  };
}
