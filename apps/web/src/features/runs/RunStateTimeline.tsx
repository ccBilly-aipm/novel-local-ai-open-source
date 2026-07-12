import type { RunStep } from "../../types";

interface Props {
  steps: RunStep[];
  state: string;
}

const labels: Record<string, string> = {
  LOAD_PROJECT: "读取项目",
  ASSEMBLE_CONTEXT: "组装上下文",
  WRITE_DRAFT: "生成初稿",
  REVISE_DRAFT: "根据反馈修订",
  CHECK_CONTINUITY: "连续性检查",
  BUILD_REVISION_PLAN: "生成修订计划",
  AI_REVIEW_ENABLED: "AI 接管审批",
  WAIT_HUMAN_APPROVAL: "等待人工审批",
  AUTO_COMMITTING: "自动写入正式正文",
  COMMITTED: "正文已写入",
  UPDATING_STORY_MEMORY: "更新故事记忆",
  MEMORY_UPDATED: "故事记忆已更新",
  PAUSED: "自动运行已暂停",
  APPROVED: "已写入正式正文",
  REJECTED: "已拒绝",
  FAILED: "运行失败",
};

export default function RunStateTimeline({ steps, state }: Props) {
  const latest = steps[steps.length - 1];
  return (
    <details className="panel shrink-0 overflow-hidden">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4">
        <div>
          <span className="font-serif text-lg font-semibold">运行时间线</span>
          <span className="ml-2 text-xs text-black/40">{steps.length} 步{latest ? ` · 最近：${labels[latest.state] || latest.state}` : ""}</span>
        </div>
        <span className="rounded-full bg-black/5 px-3 py-1 font-mono text-[10px]">{state}</span>
      </summary>
      <div className="max-h-64 space-y-1 overflow-y-auto border-t border-black/10 px-3 py-2">
        {steps.map((step) => (
          <div key={step.id} className="grid grid-cols-[20px_1fr_auto] items-start gap-2 rounded-xl px-2 py-2">
            <span className={`mt-0.5 grid h-5 w-5 place-items-center rounded-full text-[10px] text-white ${
              step.status === "failed" ? "bg-red-600" : step.status === "completed" ? "bg-moss" : "bg-blue-600"
            }`}>
              {step.status === "failed" ? "!" : step.status === "completed" ? "✓" : "•"}
            </span>
            <div>
              <div className="text-sm font-semibold">{labels[step.state] || step.state}</div>
              {step.error && <div className="mt-1 text-xs text-red-700">{step.error_code}: {step.error}</div>}
            </div>
            <time className="text-[10px] text-black/35">{new Date(step.started_at).toLocaleTimeString()}</time>
          </div>
        ))}
        {steps.length === 0 && <div className="rounded-xl bg-black/[0.03] p-4 text-sm text-black/45">尚未写入步骤日志。</div>}
      </div>
    </details>
  );
}
