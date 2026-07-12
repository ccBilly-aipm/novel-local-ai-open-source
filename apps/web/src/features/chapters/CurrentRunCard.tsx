import type { ChapterLoopRunSummary } from "../../types";

interface Props {
  run: ChapterLoopRunSummary;
  onOpen: () => void;
}

export default function CurrentRunCard({ run, onOpen }: Props) {
  return (
    <section className={`rounded-2xl border p-4 ${
      run.status === "waiting" ? "border-amber-200 bg-amber-50" :
        run.status === "failed" ? "border-red-200 bg-red-50" : "border-blue-200 bg-blue-50"
    }`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] opacity-55">Current loop run</div>
          <div className="mt-1 font-semibold">
            {run.status === "waiting" ? "草稿等待你的决定" : run.status === "failed" ? "运行失败" : "正在生成与检查"}
          </div>
          <div className="mt-1 font-mono text-[10px] opacity-55">{run.state}</div>
        </div>
        <span className="rounded-full bg-white/60 px-2 py-1 text-[10px] font-bold">{run.status}</span>
      </div>
      {run.error && <p className="mt-3 text-xs text-red-700">{run.error_code}: {run.error}</p>}
      <button className="btn-primary mt-4 w-full" onClick={onOpen}>
        {run.status === "waiting" ? "查看并审批版本" : "打开运行详情"}
      </button>
    </section>
  );
}
