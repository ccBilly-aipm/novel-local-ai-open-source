import { useEffect, useMemo, useRef, useState } from "react";
import { api, parseJson } from "../../services/api";
import type { Chapter, ChapterLoopRun, ChapterVersion, ContinuityReport, ModelProvider, RunRawOutput } from "../../types";
import ContinuityReportPanel from "./ContinuityReportPanel";
import RunDecisionBar from "./RunDecisionBar";
import RunStateTimeline from "./RunStateTimeline";
import VersionPreview from "./VersionPreview";

interface Props {
  projectId: string;
  runId: string;
  onBack: () => void;
  onChanged: () => Promise<void>;
  onOpenRun: (runId: string) => void;
}

export default function RunDetailPage({ projectId, runId, onBack, onChanged, onOpenRun }: Props) {
  const [run, setRun] = useState<ChapterLoopRun | null>(null);
  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [provider, setProvider] = useState<ModelProvider | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<ChapterVersion | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [rawOutput, setRawOutput] = useState<RunRawOutput | null>(null);
  const [showRawOutput, setShowRawOutput] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [now, setNow] = useState(Date.now());
  const previewRef = useRef<HTMLDivElement | null>(null);

  async function load() {
    const detail = await api<ChapterLoopRun>(`/projects/${projectId}/runs/${runId}`);
    setRun(detail);
    setSelectedVersion((current) =>
      detail.versions.find((version) => version.id === current?.id)
      || detail.versions.find((version) => version.id === detail.current_version_id)
      || detail.versions[detail.versions.length - 1]
      || null,
    );
    const [chapterData, providerData] = await Promise.all([
      api<Chapter>(`/chapters/${detail.chapter_id}`),
      api<ModelProvider[]>("/model-providers"),
    ]);
    setChapter(chapterData);
    setProvider(providerData.find((item) => item.id === detail.provider_id) || null);
  }

  useEffect(() => {
    void load().catch((reason) => setError(reason instanceof Error ? reason.message : "Run 加载失败"));
  }, [projectId, runId]);

  useEffect(() => {
    if (!run || !["pending", "running"].includes(run.status)) return;
    const timer = window.setInterval(() => void load(), 1000);
    return () => window.clearInterval(timer);
  }, [run?.status, runId]);

  useEffect(() => {
    if (!run || !["pending", "running"].includes(run.status)) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [run?.status]);

  useEffect(() => {
    if (autoScroll && previewRef.current) {
      previewRef.current.scrollTop = previewRef.current.scrollHeight;
    }
  }, [run?.draft_preview, autoScroll]);

  const report = useMemo(
    () => run?.continuity_report_json ? parseJson<ContinuityReport | null>(run.continuity_report_json, null) : null,
    [run?.continuity_report_json],
  );
  const failedStep = run ? [...run.steps].reverse().find((step) => step.status === "failed") : null;
  const elapsedSeconds = run?.started_at
    ? Math.max(0, Math.round(((run.finished_at ? new Date(run.finished_at).getTime() : now) - new Date(run.started_at).getTime()) / 1000))
    : 0;

  async function decide(action: "approve" | "reject" | "revise", feedback: string) {
    if (!run) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api<ChapterLoopRun>(`/projects/${projectId}/runs/${run.id}/${action}`, {
        method: "POST",
        body: JSON.stringify({ feedback }),
      });
      setRun(updated);
      setSelectedVersion(updated.versions.find((version) => version.id === updated.current_version_id) || updated.versions[updated.versions.length - 1] || null);
      await onChanged();
      if (action === "revise") window.setTimeout(() => void load(), 700);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "人工决策失败");
    } finally {
      setBusy(false);
    }
  }

  async function fetchRawOutput(): Promise<RunRawOutput> {
    if (!run) throw new Error("Run 尚未加载");
    const output = await api<RunRawOutput>(`/projects/${projectId}/runs/${run.id}/artifacts/raw-output`);
    setRawOutput(output);
    return output;
  }

  async function recoverDraft() {
    if (!run) return;
    setBusy(true);
    setError("");
    try {
      const output = rawOutput || await fetchRawOutput();
      const preview = output.content.slice(0, 1000);
      if (!window.confirm(`将以下原始输出保存为不可变候选草稿，并继续连续性检查？\n\n${preview}`)) return;
      const updated = await api<ChapterLoopRun>(`/projects/${projectId}/runs/${run.id}/recover-draft`, {
        method: "POST",
        body: JSON.stringify({ source: "raw_output", note: "用户在 Run Detail 中确认恢复原始正文" }),
      });
      setRun(updated);
      setShowRawOutput(false);
      await onChanged();
      window.setTimeout(() => void load(), 500);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "恢复草稿失败");
    } finally {
      setBusy(false);
    }
  }

  async function rerun() {
    if (!run || !window.confirm("创建一个新的 Loop Run 重新生成？旧失败记录和原始输出会保留。")) return;
    setBusy(true);
    setError("");
    try {
      const created = await api<ChapterLoopRun>(`/projects/${projectId}/runs/${run.id}/rerun`, {
        method: "POST",
        body: JSON.stringify({ note: "用户从失败页面重新生成" }),
      });
      await onChanged();
      onOpenRun(created.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "重新生成失败");
    } finally {
      setBusy(false);
    }
  }

  async function restoreVersion(version: ChapterVersion) {
    if (!run || !window.confirm(`将 v${version.version_number} 恢复为正式正文？当前正文会先保存为不可变备份。`)) return;
    setBusy(true);
    setError("");
    try {
      await api<ChapterVersion>(`/projects/${projectId}/chapters/${run.chapter_id}/versions/${version.id}/restore`, {
        method: "POST",
        body: JSON.stringify({ note: `用户从 Run Detail 恢复 v${version.version_number}` }),
      });
      await load();
      await onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "版本恢复失败");
    } finally {
      setBusy(false);
    }
  }

  async function controlPausedRun(action: "resume" | "abort") {
    if (!run) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api<ChapterLoopRun>(`/projects/${projectId}/runs/${run.id}/${action}`, {
        method: "POST",
        body: JSON.stringify({
          note: `用户从 Run Detail 请求 ${action}`,
          additional_revision_rounds: action === "resume" ? 1 : 0,
        }),
      });
      setRun(updated);
      await onChanged();
      if (action === "resume") window.setTimeout(() => void load(), 500);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Run 操作失败");
    } finally {
      setBusy(false);
    }
  }

  async function enableAiReview() {
    if (!run || !window.confirm(
      "AI 将把连续性报告中的问题作为定向修订要求，生成新版本并复检；通过阈值后自动写入正式正文。blocker 或达到修订上限时仍会暂停。继续吗？",
    )) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api<ChapterLoopRun>(`/projects/${projectId}/runs/${run.id}/auto-continue`, {
        method: "POST",
        body: JSON.stringify({
          note: "用户在 Run Detail 中授权 AI 接管连续性报告、自动修订并写入",
          additional_revision_rounds: 3,
        }),
      });
      setRun(updated);
      setSelectedVersion(updated.versions.find((version) => version.id === updated.current_version_id) || updated.versions[updated.versions.length - 1] || null);
      await onChanged();
      window.setTimeout(() => void load(), 500);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "AI 接管失败");
    } finally {
      setBusy(false);
    }
  }

  async function copyDiagnosis() {
    if (!run) return;
    const diagnostic = [
      `run_id=${run.id}`,
      `state=${run.state}`,
      `status=${run.status}`,
      `failed_step=${run.failed_step || ""}`,
      `error_code=${run.error_code}`,
      `technical_error=${run.technical_error}`,
      `provider=${provider?.name || ""}`,
      `model=${provider?.model || ""}`,
      `draft_chars=${run.draft_chars}`,
      `attempts=${run.draft_attempts_json}`,
    ].join("\n");
    await navigator.clipboard.writeText(diagnostic);
    setError("诊断信息已复制到剪贴板。");
  }

  if (!run) {
    return <main className="mx-auto max-w-7xl p-8">{error || "正在加载 Run..."}</main>;
  }

  return (
    <main className="mx-auto max-w-7xl p-7">
      <button className="mb-5 text-sm font-semibold text-black/45 hover:text-moss" onClick={onBack}>← 返回运行列表</button>
      <header className="mb-6 flex items-end justify-between gap-5">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-rust">Chapter loop run</div>
          <h1 className="mt-1 font-serif text-3xl font-semibold">{chapter?.title || run.chapter_id}</h1>
          <p className="mt-2 text-sm text-black/45">
            {provider ? `${provider.name} · ${provider.model}` : "Provider 已删除或不可用"} · {run.context_budget} tokens · 创建于 {new Date(run.created_at).toLocaleString()}
          </p>
        </div>
        <span className={`rounded-full px-4 py-2 text-xs font-bold ${
          run.status === "waiting" ? "bg-amber-100 text-amber-800" :
            run.status === "failed" ? "bg-red-100 text-red-700" :
              run.status === "approved" ? "bg-green-100 text-green-700" : "bg-blue-100 text-blue-700"
        }`}>{run.status}</span>
      </header>

      {error && <div className="mb-5 rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</div>}
      {run.status === "failed" && (
        <section className="mb-5 rounded-2xl border border-red-200 bg-red-50 p-5 text-red-800">
          <div className="font-bold">{run.error_code || "LOOP_FAILED"}</div>
          <p className="mt-1 text-sm">{run.user_facing_error || run.error}</p>
          {failedStep && <p className="mt-2 text-xs">失败步骤：{failedStep.state} · {failedStep.error_code}</p>}
          <div className="mt-4 flex flex-wrap gap-2">
            {run.recovery_actions.includes("view_raw_output") && (
              <button className="btn-soft" onClick={() => void fetchRawOutput().then(() => setShowRawOutput(true))}>查看原始输出</button>
            )}
            {run.recovery_actions.includes("recover_draft") && (
              <button className="btn-primary" disabled={busy} onClick={() => void recoverDraft()}>保存原始输出为草稿</button>
            )}
            {run.recovery_actions.includes("rerun") && (
              <button className="btn-soft" disabled={busy} onClick={() => void rerun()}>重新生成</button>
            )}
            <button className="btn-soft" onClick={() => { window.location.hash = "/models"; }}>检查模型配置</button>
            <button className="btn-soft" onClick={() => void copyDiagnosis()}>复制诊断信息</button>
          </div>
          <details className="mt-4 text-xs">
            <summary className="cursor-pointer font-semibold">技术详情</summary>
            <pre className="mt-2 whitespace-pre-wrap rounded-xl bg-white/60 p-3">{run.technical_error}</pre>
          </details>
        </section>
      )}
      {run.status === "approved" && (
        <div className="mb-5 rounded-xl bg-green-50 p-4 text-sm text-green-800">当前批准版本已经写入正式章节正文。</div>
      )}
      {run.status === "committed" && (
        <div className="mb-5 rounded-xl bg-green-50 p-4 text-sm text-green-800">
          自动策略已通过阈值，当前版本已写入正式正文，并生成章节摘要与 Story Memory。
        </div>
      )}
      {run.status === "paused" && (
        <div className="mb-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <b>自动运行已暂停</b>
          <p className="mt-1">{run.auto_policy?.pause_reason || run.error || "需要人工检查后重新运行。"}</p>
          <p className="mt-2 text-xs">正式正文未因暂停而自动写入。</p>
          <div className="mt-3 flex gap-2">
            <button className="btn-primary" disabled={busy} onClick={() => void controlPausedRun("resume")}>
              {run.auto_policy && run.auto_policy.revision_rounds >= run.auto_policy.max_revision_rounds_per_chapter
                ? "追加 1 轮自动修订"
                : "修复后继续"}
            </button>
            <button className="btn-soft" disabled={busy} onClick={() => void controlPausedRun("abort")}>终止此 Run</button>
          </div>
        </div>
      )}
      {run.status === "rejected" && (
        <div className="mb-5 rounded-xl bg-black/5 p-4 text-sm text-black/60">此候选版本已拒绝，正式正文没有被修改。</div>
      )}
      {run.status === "waiting" && run.state === "WAIT_HUMAN_APPROVAL" && !(
        run.auto_policy && ["ai_auto_revise", "ai_auto_commit", "full_autonomous"].includes(run.auto_policy.mode)
      ) && (
        <section className="mb-5 flex items-center justify-between gap-5 rounded-2xl border border-blue-200 bg-blue-50 p-4 text-blue-950">
          <div>
            <b>当前 Run 仍是人工审批模式</b>
            <p className="mt-1 text-xs leading-5">
              可交给 AI 读取连续性报告，逐项定向修订并复检；通过安全阈值后自动写入，原版本和正文备份都会保留。
            </p>
          </div>
          <button className="btn-primary shrink-0" disabled={busy} onClick={() => void enableAiReview()}>
            {busy ? "正在接管..." : "交给 AI 自动处理"}
          </button>
        </section>
      )}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.55fr)]">
        <div className="min-w-0 lg:h-[760px]">
          {(run.current_step === "WRITE_DRAFT" || run.partial_output_available) && !selectedVersion && (
            <section className="panel flex h-full min-h-0 flex-col overflow-hidden">
              <header className="flex items-start justify-between border-b border-black/10 px-5 py-4">
                <div>
                  <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-rust">Live draft preview</div>
                  <h2 className="mt-1 font-serif text-xl font-semibold">
                    {run.status === "failed" ? "已保留的生成内容" : "正在生成初稿"}
                  </h2>
                  <p className="mt-1 text-xs text-black/45">
                    {provider?.model || "本地模型"} · {run.draft_chars} 字符 · {elapsedSeconds} 秒
                    {run.draft_preview_updated_at ? ` · 更新于 ${new Date(run.draft_preview_updated_at).toLocaleTimeString()}` : ""}
                  </p>
                </div>
                <label className="flex items-center gap-2 text-xs text-black/50">
                  <input type="checkbox" checked={autoScroll} onChange={(event) => setAutoScroll(event.target.checked)} />
                  自动滚动
                </label>
              </header>
              {!run.stream_supported && run.status === "running" && (
                <div className="bg-amber-50 px-5 py-3 text-xs text-amber-900">当前 Provider 不支持流式输出，正在等待完整结果。</div>
              )}
              {run.stream_supported && run.status === "running" && (
                <div className="bg-blue-50 px-5 py-3 text-xs text-blue-800">
                  {run.is_streaming ? "正在接收本地模型增量正文..." : "模型请求已启动，等待首段正文..."}
                </div>
              )}
              <div ref={previewRef} className="min-h-0 flex-1 overflow-y-auto whitespace-pre-wrap px-7 py-6 font-serif text-base leading-8">
                {run.draft_preview}
              </div>
            </section>
          )}
          {(selectedVersion || !(run.current_step === "WRITE_DRAFT" || run.partial_output_available)) && (
            <VersionPreview
              version={selectedVersion}
              versions={run.versions}
              approvedVersionId={run.approved_version_id}
              onSelect={setSelectedVersion}
              onRestore={(version) => void restoreVersion(version)}
              autoCommitEnabled={Boolean(run.auto_policy && ["ai_auto_commit", "full_autonomous"].includes(run.auto_policy.mode))}
              className="h-full"
            />
          )}
        </div>
        <div className="min-w-0 space-y-4 overflow-y-auto pr-1 lg:h-[760px]">
          {run.auto_policy && (
            <section className="panel p-5">
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-rust">Auto run policy</div>
              <h2 className="mt-1 font-serif text-xl font-semibold">自动策略</h2>
              <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                <div className="rounded-lg bg-black/[0.03] p-3"><b>模式</b><br />{run.auto_policy.mode}</div>
                <div className="rounded-lg bg-black/[0.03] p-3"><b>修订轮次</b><br />{run.auto_policy.revision_rounds} / {run.auto_policy.max_revision_rounds_per_chapter}</div>
              </div>
              {run.auto_policy.reference_pack_id && <p className="mt-3 text-xs text-moss">本次上下文使用了用户显式 Reference Pack。</p>}
            </section>
          )}
          <RunStateTimeline steps={run.steps} state={run.state} />
          <ContinuityReportPanel
            report={report}
            autoRevisionEnabled={Boolean(run.auto_policy && ["ai_auto_revise", "ai_auto_commit", "full_autonomous"].includes(run.auto_policy.mode))}
            revisionRounds={run.auto_policy?.revision_rounds || 0}
            maxRevisionRounds={run.auto_policy?.max_revision_rounds_per_chapter || 0}
          />
          {run.revision_plans.length > 0 && (
            <section className="panel p-5">
              <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-rust">Revision plan</div>
              <h2 className="mt-1 font-serif text-xl font-semibold">自动修订计划</h2>
              <div className="mt-3 space-y-3">
                {run.revision_plans.map((plan, index) => (
                  <details key={plan.id} className="rounded-xl border border-black/10 bg-white/55 p-3 text-xs" open={index === run.revision_plans.length - 1}>
                    <summary className="cursor-pointer font-semibold">第 {index + 1} 轮 · {plan.status}</summary>
                    <pre className="mt-3 whitespace-pre-wrap rounded-lg bg-black/[0.03] p-3">{JSON.stringify(parseJson(plan.fixes_json, []), null, 2)}</pre>
                  </details>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>

      <details className="panel mt-5 p-5">
        <summary className="cursor-pointer font-semibold">高级日志 · {run.model_calls.length} 次模型调用</summary>
        <div className="mt-4 space-y-4">
          {run.model_calls.map((call) => (
            <details key={call.id} className="rounded-xl border border-black/10 bg-white/55 p-4 text-xs">
              <summary className="cursor-pointer font-semibold">
                {call.agent_name} · {call.status} · {call.duration_ms ?? "-"} ms {call.error_code && `· ${call.error_code}`}
              </summary>
              <div className="mt-3 grid grid-cols-3 gap-2 rounded-xl bg-black/[0.03] p-3 text-[10px]">
                <div><b>Provider</b><br />{provider?.name || call.provider_id || "-"}</div>
                <div><b>Model</b><br />{provider?.model || "-"}</div>
                <div><b>Tokens / chars</b><br />{call.input_tokens ?? "-"} / {call.output_tokens ?? "-"} / {call.response.length}</div>
              </div>
              <div className="label mt-4">Prompt</div>
              <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-ink p-3 text-[10px] leading-5 text-white/70">{call.prompt}</pre>
              <div className="label mt-4">Raw response / error</div>
              <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-black/5 p-3 text-[10px] leading-5">{call.response || call.error}</pre>
              <div className="label mt-4">Parsed result / Guard</div>
              <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-black/5 p-3 text-[10px] leading-5">{call.parsed_json || "未产生解析结果"}</pre>
              <div className="label mt-4">Provider raw payload</div>
              <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-black/5 p-3 text-[10px] leading-5">{call.raw_response_json}</pre>
            </details>
          ))}
          {run.draft_attempts_json !== "[]" && (
            <details className="rounded-xl border border-black/10 bg-white/55 p-4 text-xs">
              <summary className="cursor-pointer font-semibold">草稿校验与重试记录</summary>
              <pre className="mt-3 whitespace-pre-wrap rounded-lg bg-black/5 p-3 text-[10px] leading-5">{run.draft_attempts_json}</pre>
            </details>
          )}
        </div>
      </details>

      {showRawOutput && rawOutput && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/45 p-6" onMouseDown={() => setShowRawOutput(false)}>
          <section className="panel max-h-[85vh] w-full max-w-4xl overflow-hidden" onMouseDown={(event) => event.stopPropagation()}>
            <header className="flex items-center justify-between border-b border-black/10 px-5 py-4">
              <div><b>原始 Writer 输出</b><div className="text-xs text-black/40">{rawOutput.characters} 字符 · {rawOutput.agent_name}</div></div>
              <button className="text-xl text-black/40" onClick={() => setShowRawOutput(false)}>×</button>
            </header>
            <pre className="max-h-[65vh] overflow-y-auto whitespace-pre-wrap p-6 font-serif text-sm leading-7">{rawOutput.content}</pre>
            <footer className="flex justify-end gap-2 border-t border-black/10 p-4">
              <button className="btn-soft" onClick={() => void navigator.clipboard.writeText(rawOutput.content)}>复制原始输出</button>
              {run.recovery_actions.includes("recover_draft") && <button className="btn-primary" onClick={() => void recoverDraft()}>保存为候选草稿</button>}
            </footer>
          </section>
        </div>
      )}

      {run.state === "WAIT_HUMAN_APPROVAL" && run.status === "waiting" && (
        <div className="mt-5">
          <RunDecisionBar
            disabled={false}
            busy={busy}
            onApprove={(feedback) => decide("approve", feedback)}
            onReject={(feedback) => decide("reject", feedback)}
            onRevise={(feedback) => decide("revise", feedback)}
          />
        </div>
      )}
    </main>
  );
}
