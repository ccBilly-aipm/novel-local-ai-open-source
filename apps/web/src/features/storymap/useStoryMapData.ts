import { useCallback, useEffect, useState } from "react";
import { api } from "../../services/api";
import type { StoryMap } from "../../types";

interface StoryMapDataState {
  data: StoryMap | null;
  loading: boolean;
  error: string;
  refetch: () => Promise<void>;
}

// GET /api/novels/{novelId}/story-map，一次拉齐 + refetch()。
export function useStoryMapData(novelId: string): StoryMapDataState {
  const [data, setData] = useState<StoryMap | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api<StoryMap>(`/novels/${novelId}/story-map`);
      setData(result);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "加载故事地图失败");
    } finally {
      setLoading(false);
    }
  }, [novelId]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  return { data, loading, error, refetch };
}
