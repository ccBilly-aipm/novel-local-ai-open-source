import { useState } from "react";
import type { ContinuityReport } from "../../types";

interface Props {
  report: ContinuityReport | null;
  autoRevisionEnabled?: boolean;
  revisionRounds?: number;
  maxRevisionRounds?: number;
}

export default function ContinuityReportPanel({
  report,
  autoRevisionEnabled = false,
  revisionRounds = 0,
  maxRevisionRounds = 0,
}: Props) {
  const [expandedIssues, setExpandedIssues] = useState<number[]>([]);
  if (!report) {
    return <section className="panel shrink-0 p-5 text-sm text-black/45">连续性检查尚无可显示结果。</section>;
  }
  return (
    <section className="panel shrink-0 overflow-hidden">
      <div className="flex items-start justify-between gap-4">
        <div className="px-5 pt-5">
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-rust">Continuity checker</div>
          <h2 className="mt-1 font-serif text-xl font-semibold">连续性报告</h2>
        </div>
        <span className={`mr-5 mt-5 rounded-full px-3 py-1 text-xs font-bold ${
          report.passed ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
        }`}>
          {report.passed ? "检查通过" : `需要处理 · ${report.severity}`}
        </span>
      </div>
      {autoRevisionEnabled && !report.passed && (
        <div className="mx-5 mt-4 rounded-xl bg-blue-50 p-3 text-xs leading-5 text-blue-900">
          AI 自动迭代已开启。报告中的问题、证据和建议会直接进入 RevisionPlan，由 RevisionWriter 定向修改后复检；
          当前修订轮次 {revisionRounds} / {maxRevisionRounds}。
        </div>
      )}
      <div className="mt-4 max-h-[430px] space-y-2 overflow-y-auto border-t border-black/10 p-4">
        {report.issues.map((issue, index) => (
          <article key={`${issue.type}-${index}`} className="rounded-xl border border-black/10 bg-white/55 text-xs leading-5">
            <button
              type="button"
              className="flex w-full items-center justify-between gap-3 p-3 text-left"
              onClick={() => setExpandedIssues((current) =>
                current.includes(index)
                  ? current.filter((item) => item !== index)
                  : [...current, index]
              )}
            >
              <div className="min-w-0">
                <b>{issue.type}</b>
                <span className="ml-2 line-clamp-1 text-black/50">{issue.problem}</span>
              </div>
              <span className="shrink-0 uppercase text-rust">
                {issue.severity} · {expandedIssues.includes(index) ? "收起" : "展开"}
              </span>
            </button>
            {expandedIssues.includes(index) && (
              <div className="border-t border-black/10 px-4 py-3">
                <p><b>问题：</b>{issue.problem}</p>
                <p><b>证据：</b>{issue.evidence}</p>
                <p><b>建议：</b>{issue.suggested_fix}</p>
                {issue.auto_fixable !== undefined && (
                  <p>
                    <b>自动修复：</b>
                    {issue.must_pause || issue.severity === "blocker"
                      ? "必须暂停"
                      : autoRevisionEnabled
                        ? issue.auto_fixable ? "将自动修复" : "Checker 建议人工处理，但自动模式仍会尝试"
                        : issue.auto_fixable ? "允许" : "需要人工处理"}
                  </p>
                )}
              </div>
            )}
          </article>
        ))}
        {report.issues.length === 0 && <div className="rounded-xl bg-green-50 p-4 text-sm text-green-800">未报告结构化冲突。</div>}
      </div>
    </section>
  );
}
