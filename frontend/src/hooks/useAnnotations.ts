/* useAnnotations.ts — 批注列表状态与持久化 */
import { useCallback, useEffect, useState } from "react";
import type { Annotation, Anchor } from "../types";
import {
  createAnnotation,
  deleteAnnotation,
  fetchAnnotations,
} from "../api/client";

export function useAnnotations(paperId: string | null) {
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!paperId) {
      setAnnotations([]);
      return;
    }
    setLoading(true);
    try {
      setAnnotations(await fetchAnnotations(paperId));
    } catch {
      setAnnotations([]);
    } finally {
      setLoading(false);
    }
  }, [paperId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const add = useCallback(
    async (body: {
      page: number | null;
      quote: string;
      note: string;
      anchor: Anchor;
    }) => {
      if (!paperId) return;
      const created = await createAnnotation(paperId, body);
      setAnnotations((prev) => [...prev, created]);
    },
    [paperId],
  );

  const remove = useCallback(async (id: string) => {
    await deleteAnnotation(id);
    setAnnotations((prev) => prev.filter((a) => a.id !== id));
  }, []);

  return { annotations, loading, refresh, add, remove };
}
