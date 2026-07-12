import { useMemo, useState } from "react";
import type { ChapterLoopRunSummary } from "../../types";
import MultiChapterRunsPanel from "./MultiChapterRunsPanel";

interface Props {
  runs: ChapterLoopRunSummary[];
  title?: string;
  projectId?: string;
  onOpen: (run: ChapterLoopRunSummary) => void;
  onOpenRunId?: (runId: string) => void;
}

const filters = ["all", "waiting", "running", "paused", "failed", "approved", "committed", "rejected"] as const;

export default function RunListPage({ runs, title = "运行记录", projectId, onOpen, onOpenRunId }: Props) {
  const [filter, setFilter] = useState<(typeof filters)[number]>("all");
  const visible = useMemo(
    () => filter === "all"
      ? runs
      : filter === "running"
        ? runs.filter((run) => run.status === "running" || run.status === "pending")
        : runs.filter((run) => run.status === filter),
    [runs, filter],
  );

  return (
    <main className="mx-auto max-w-7xl p-8">
      <div className="mb-7">
        <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-rust">Loop runs</div>
        <h1 className="mt-1 font-serif text-4xl font-semibold">{title}</h1>
        <p className="mt-2 text-sm text-black/50">查看待审批、运行中和失败任务；完整 prompt 与模型输出只在详情页展开。</p>
      </div>
      <div className="mb-5 flex gap-2">
        {filters.map((item) => (
          <button
            key={item}
            className={`rounded-full px-4 py-2 text-xs font-semibold ${filter === item ? "bg-ink text-white" : "bg-white/60 text-black/50"}`}
            onClick={() => setFilter(item)}
          >
            {item === "all" ? "全部" : item}
          </button>
        ))}
      </div>
      {projectId && <MultiChapterRunsPanel projectId={projectId} chapterRuns={runs} onOpenChild={(runId) => {
        const run = runs.find((item) => item.id === runId);
        if (run) onOpen(run);
        else onOpenRunId?.(runId);
      }} />}
      <section className="panel overflow-hidden">
        {visible.map((run) => (
          <button
            key={run.id}
            className="grid w-full grid-cols-[1.3fr_1fr_0.8fr_0.7fr_auto] items-center gap-4 border-b border-black/5 px-5 py-4 text-left last:border-0 hover:bg-white/60"
            onClick={() => onOpen(run)}
          >
            <div><b>{run.chapter_title}</b><div className="text-xs text-black/40">{run.project_name} · {run.novel_title}</div></div>
            <div className="truncate text-xs text-black/50">
              {run.provider_name || "Provider 已删除"} · {run.model || "-"}
              {run.error_code && <div className="mt-1 font-mono text-[10px] text-red-700">{run.error_code}</div>}
            </div>
            <span className="font-mono text-[10px] text-black/45">{run.state}</span>
            <span className={`w-fit rounded-full px-2 py-1 text-[10px] font-bold ${
              run.status === "waiting" ? "bg-amber-100 text-amber-800" :
                run.status === "paused" ? "bg-amber-100 text-amber-800" :
                run.status === "failed" ? "bg-red-100 text-red-700" :
                  ["approved", "committed"].includes(run.status) ? "bg-green-100 text-green-700" : "bg-blue-100 text-blue-700"
            }`}>{run.status}</span>
            <span className="text-xs text-black/35">{new Date(run.updated_at).toLocaleString()}</span>
          </button>
        ))}
        {visible.length === 0 && <div className="p-12 text-center text-sm text-black/40">此筛选条件下没有 Loop Run。</div>}
      </section>
    </main>
  );
}
