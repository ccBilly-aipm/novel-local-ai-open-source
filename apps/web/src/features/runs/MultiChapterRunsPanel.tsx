import { useEffect, useMemo, useState } from "react";
import { ApiError, api, parseJson } from "../../services/api";
import type { ChapterLoopRunSummary, MultiChapterRun } from "../../types";

interface Props {
  projectId: string;
  chapterRuns: ChapterLoopRunSummary[];
  onOpenChild: (runId: string) => void;
}

const terminalStatuses = new Set(["completed", "stopped", "failed"]);

function actionError(reason: unknown) {
  if (reason instanceof ApiError && reason.detail && typeof reason.detail === "object") {
    const detail = reason.detail as Record<string, unknown>;
    if (typeof detail.message === "string") {
      return typeof detail.code === "string" ? `${detail.code}: ${detail.message}` : detail.message;
    }
  }
  return reason instanceof Error ? reason.message : "生产线操作失败";
}

export default function MultiChapterRunsPanel({ projectId, chapterRuns, onOpenChild }: Props) {
  const [runs, setRuns] = useState<MultiChapterRun[]>([]);
  const [busyId, setBusyId] = useState("");
  const [loadError, setLoadError] = useState("");
  const [actionErrors, setActionErrors] = useState<Record<string, string>>({});

  async function load() {
    setRuns(await api<MultiChapterRun[]>(`/projects/${projectId}/multi-chapter-runs`));
    setLoadError("");
  }

  useEffect(() => {
    void load().catch((reason) => setLoadError(reason instanceof Error ? reason.message : "生产线加载失败"));
  }, [projectId]);

  const polling = useMemo(
    () => runs.some((run) => ["pending", "running", "waiting_human"].includes(run.status)),
    [runs],
  );

  useEffect(() => {
    if (!polling) return;
    const timer = window.setInterval(() => void load(), 1500);
    return () => window.clearInterval(timer);
  }, [polling, projectId]);

  async function act(run: MultiChapterRun, action: "pause" | "resume" | "stop") {
    setBusyId(run.id);
    setActionErrors((current) => ({ ...current, [run.id]: "" }));
    try {
      await api<MultiChapterRun>(`/projects/${projectId}/multi-chapter-runs/${run.id}/${action}`, {
        method: "POST",
        body: JSON.stringify({
          note: `用户从运行列表请求 ${action}`,
          additional_revision_rounds: action === "resume" ? 1 : 0,
        }),
      });
      await load();
    } catch (reason) {
      setActionErrors((current) => ({ ...current, [run.id]: actionError(reason) }));
    } finally {
      setBusyId("");
    }
  }

  if (runs.length === 0 && !loadError) return null;

  const activeRun = runs.find((run) => run.active_slot === 1 && !terminalStatuses.has(run.status));

  return (
    <section className="mb-7">
      <div className="mb-3">
        <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-rust">Multi chapter pipeline</div>
        <h2 className="mt-1 font-serif text-2xl font-semibold">自动章节生产线</h2>
      </div>
      {loadError && <div className="mb-3 rounded-xl bg-red-50 p-3 text-sm text-red-700">{loadError}</div>}
      <div className="space-y-3">
        {runs.map((run) => {
          const completed = parseJson<string[]>(run.completed_chapter_ids_json, []).length;
          const policy = parseJson<Record<string, unknown>>(run.policy_json, {});
          const providerAttempts = Array.isArray(policy.provider_attempts)
            ? policy.provider_attempts.map(String)
            : [];
          const percent = Math.min(100, Math.round((completed / Math.max(1, run.chapter_count)) * 100));
          const child = chapterRuns.find((item) => item.id === run.current_loop_run_id);
          const childWaiting = run.status === "waiting_human" && child?.status === "waiting";
          const childApproved = run.status === "waiting_human" && ["approved", "committed"].includes(child?.status || "");
          const conflictingRun = run.status === "paused" && activeRun && activeRun.id !== run.id
            ? activeRun
            : null;
          const statusMessage = run.status === "waiting_human"
            ? "当前章节已生成，正在等待人工审批。"
            : terminalStatuses.has(run.status) && !run.error_code
              ? ""
              : run.pause_reason || run.error;
          return (
            <article key={run.id} className="panel p-5">
              <div className="flex items-start justify-between gap-5">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <b>{run.chapter_count} 章生产线</b>
                    <span className={`rounded-full px-2 py-1 text-[10px] font-bold ${
                      run.status === "completed" ? "bg-green-100 text-green-700"
                        : run.status === "paused" || run.status === "waiting_human" ? "bg-amber-100 text-amber-800"
                          : run.status === "failed" ? "bg-red-100 text-red-700"
                            : "bg-blue-100 text-blue-700"
                    }`}>{run.status}</span>
                    <span className="text-xs text-black/40">{run.mode}</span>
                  </div>
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-black/5">
                    <div className="h-full bg-moss transition-all" style={{ width: `${percent}%` }} />
                  </div>
                  <p className="mt-2 text-xs text-black/50">
                    已完成 {completed} / {run.chapter_count} 章
                    {run.current_chapter_id ? ` · 当前章节 ${run.current_index + 1}` : ""}
                    {run.current_loop_run_id ? " · 子 Run 可查看" : ""}
                  </p>
                  {statusMessage && (
                    <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
                      {run.error_code && <b className="mr-2 font-mono">{run.error_code}</b>}
                      {statusMessage}
                    </div>
                  )}
                  {childWaiting && (
                    <div className="mt-3 rounded-lg bg-blue-50 px-3 py-2 text-xs text-blue-900">
                      这不是生成故障。当前章节已经生成完成，正在等待你批准、拒绝或请求修订。
                    </div>
                  )}
                  {conflictingRun && (
                    <div className="mt-3 rounded-lg bg-blue-50 px-3 py-2 text-xs text-blue-900">
                      暂时不能恢复：同一本小说已有一条 {conflictingRun.status} 生产线。
                      请先处理上方当前生产线，完成或终止后再恢复此历史任务。
                    </div>
                  )}
                  {actionErrors[run.id] && (
                    <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
                      {actionErrors[run.id]}
                    </div>
                  )}
                  {providerAttempts.length > 1 && (
                    <details className="mt-3 rounded-lg bg-blue-50 px-3 py-2 text-xs text-blue-900">
                      <summary className="cursor-pointer font-semibold">模型服务自动恢复记录</summary>
                      <ul className="mt-2 space-y-1">
                        {providerAttempts.map((attempt, index) => <li key={`${run.id}-${index}`}>{attempt}</li>)}
                      </ul>
                    </details>
                  )}
                </div>
                <div className="flex flex-wrap justify-end gap-2">
                  {run.current_loop_run_id && (
                    <button className="btn-soft" onClick={() => onOpenChild(run.current_loop_run_id!)}>
                      {childWaiting ? "查看并审批当前章节" : "查看当前章节"}
                    </button>
                  )}
                  {["pending", "running"].includes(run.status) && (
                    <button className="btn-soft" disabled={busyId === run.id} onClick={() => void act(run, "pause")}>暂停</button>
                  )}
                  {run.status === "paused" && (
                    <button
                      className="btn-primary"
                      disabled={busyId === run.id || Boolean(conflictingRun)}
                      onClick={() => void act(run, "resume")}
                    >
                      {conflictingRun ? "等待当前生产线结束" : "恢复 / 追加修订"}
                    </button>
                  )}
                  {childApproved && (
                    <button className="btn-primary" disabled={busyId === run.id} onClick={() => void act(run, "resume")}>
                      继续下一章
                    </button>
                  )}
                  {!terminalStatuses.has(run.status) && (
                    <button className="btn-soft" disabled={busyId === run.id} onClick={() => void act(run, "stop")}>终止</button>
                  )}
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
