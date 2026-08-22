/* useAnnotations.ts — 结果批注状态与持久化（按 run 键控） */
import { useCallback, useEffect, useState } from "react";
import type { Annotation } from "../types";
import {
  createRunAnnotation,
  deleteAnnotation,
  fetchRunAnnotations,
} from "../api/client";

export function useAnnotations(runId: string | null) {
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!runId) {
      setAnnotations([]);
      return;
    }
    setLoading(true);
    try {
      setAnnotations(await fetchRunAnnotations(runId));
    } catch {
      setAnnotations([]);
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const add = useCallback(
    async (body: {
      record_index: number;
      field?: string | null;
      note: string;
      value_snapshot?: string | null;
    }) => {
      if (!runId) return;
      const created = await createRunAnnotation(runId, body);
      setAnnotations((prev) => [...prev, created]);
    },
    [runId],
  );

  const remove = useCallback(async (id: string) => {
    await deleteAnnotation(id);
    setAnnotations((prev) => prev.filter((a) => a.id !== id));
  }, []);

  return { annotations, loading, refresh, add, remove };
}
