import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, parseJson } from "../services/api";
import type {
  CanonState,
  Chapter,
  Character,
  ContextPreview,
  GenerationRun,
  ModelProvider,
  Novel,
  ReviewResult,
  WritingTask,
} from "../types";

interface Props {
  novel: Novel;
  onNovelChange: (novel: Novel) => void;
}

const terminalStatuses = new Set(["completed", "failed", "paused"]);

export default function Workspace({ novel, onNovelChange }: Props) {
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [chapterForm, setChapterForm] = useState({
    title: "",
    goal: "",
    outline: "",
    content: "",
    characterIds: [] as string[],
  });
  const [novelForm, setNovelForm] = useState({
    synopsis: novel.synopsis,
    story_outline: novel.story_outline,
    style_guide: novel.style_guide,
    forbidden_content: novel.forbidden_content,
  });
  const [providerId, setProviderId] = useState("");
  const [budget, setBudget] = useState(6000);
  const [task, setTask] = useState<WritingTask | null>(null);
  const [context, setContext] = useState<ContextPreview | null>(null);
  const [runs, setRuns] = useState<GenerationRun[]>([]);
  const [reviews, setReviews] = useState<ReviewResult[]>([]);
  const [canon, setCanon] = useState<CanonState | null>(null);
  const [canonStates, setCanonStates] = useState("{}");
  const [pendingUpdates, setPendingUpdates] = useState("[]");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const selected = useMemo(
    () => chapters.find((chapter) => chapter.id === selectedId) || null,
    [chapters, selectedId],
  );

  async function loadCore() {
    const [chapterData, characterData, providerData, canonData] = await Promise.all([
      api<Chapter[]>(`/novels/${novel.id}/chapters`),
      api<Character[]>(`/novels/${novel.id}/characters`),
      api<ModelProvider[]>("/model-providers"),
      api<CanonState>(`/novels/${novel.id}/canon-state`),
    ]);
    setChapters(chapterData);
    setCharacters(characterData);
    setProviders(providerData.filter((item) => item.enabled));
    setCanon(canonData);
    setCanonStates(canonData.character_states_json);
    setPendingUpdates(canonData.pending_character_updates_json);
    if (!selectedId && chapterData.length) setSelectedId(chapterData[0].id);
    if (!providerId && providerData.length) {
      const enabled = providerData.find((item) => item.enabled);
      if (enabled) setProviderId(enabled.id);
    }
  }

  async function loadChapterDetails(chapterId: string) {
    const [runData, reviewData, contextData] = await Promise.all([
      api<GenerationRun[]>(`/chapters/${chapterId}/generation-runs`),
      api<ReviewResult[]>(`/chapters/${chapterId}/reviews`),
      api<ContextPreview>(`/chapters/${chapterId}/context-preview?budget=${budget}`),
    ]);
    setRuns(runData);
    setReviews(reviewData);
    setContext(contextData);
  }

  useEffect(() => {
    void loadCore().catch((reason) => setError(reason instanceof Error ? reason.message : "加载失败"));
  }, [novel.id]);

  useEffect(() => {
    if (!selected) return;
    setChapterForm({
      title: selected.title,
      goal: selected.outline?.goal || "",
      outline: selected.outline?.outline_content || "",
      content: selected.content,
      characterIds: parseJson<string[]>(selected.outline?.character_ids_json || "[]", []),
    });
    void loadChapterDetails(selected.id).catch((reason) =>
      setError(reason instanceof Error ? reason.message : "加载章节失败"),
    );
  }, [selected?.id, selected?.updated_at]);

  async function saveNovel() {
    const updated = await api<Novel>(`/novels/${novel.id}`, {
      method: "PATCH",
      body: JSON.stringify(novelForm),
    });
    onNovelChange(updated);
    setMessage("总纲与写作约束已保存");
  }

  async function addChapter() {
    const created = await api<Chapter>("/chapters", {
      method: "POST",
      body: JSON.stringify({
        novel_id: novel.id,
        title: `第 ${chapters.length + 1} 章`,
        outline: { goal: "", outline_content: "", character_ids: [] },
      }),
    });
    await loadCore();
    setSelectedId(created.id);
  }

  async function saveChapter(event?: FormEvent) {
    event?.preventDefault();
    if (!selected) return;
    const updated = await api<Chapter>(`/chapters/${selected.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        title: chapterForm.title,
        content: chapterForm.content,
        outline: {
          goal: chapterForm.goal,
          outline_content: chapterForm.outline,
          character_ids: chapterForm.characterIds,
          required_plot_points: parseJson(selected.outline?.required_plot_points_json || "[]", []),
          location_ids: parseJson(selected.outline?.location_ids_json || "[]", []),
          style_notes: selected.outline?.style_notes || "",
        },
      }),
    });
    setChapters((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    setMessage("章节已保存，后续生成将使用当前正文");
    await loadChapterDetails(updated.id);
  }

  async function waitUntilIdle(chapterId: string, firstTask: WritingTask) {
    let current = firstTask;
    for (let count = 0; count < 360; count += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
      current = await api<WritingTask>(`/writing-tasks/${current.id}`);
      setTask(current);
      if (!terminalStatuses.has(current.status)) continue;
      const chapterTasks = await api<WritingTask[]>(`/writing-tasks?chapter_id=${chapterId}`);
      const followUp = chapterTasks.find((item) => item.status === "running" || item.status === "pending");
      if (followUp) {
        current = followUp;
        setTask(followUp);
        continue;
      }
      break;
    }
    await loadCore();
    await loadChapterDetails(chapterId);
  }

  async function runOperation(operation: "generate" | "summarize" | "review" | "character-state-update") {
    if (!selected || !providerId) return;
    setError("");
    setMessage("任务已进入本地串行队列");
    try {
      const created = await api<WritingTask>(`/chapters/${selected.id}/${operation}`, {
        method: "POST",
        body: JSON.stringify({
          provider_id: providerId,
          context_budget: budget,
          options: {
            temperature: operation === "generate" ? 0.75 : 0.2,
            ...(operation === "generate" ? {} : { max_tokens: 1600 }),
          },
        }),
      });
      setTask(created);
      await waitUntilIdle(selected.id, created);
      setMessage(created.status === "failed" ? "任务失败，请查看运行记录" : "任务链已结束");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "任务失败");
    }
  }

  async function applyPendingCharacterUpdates() {
    const updates = parseJson<Array<{ character_id?: string; changes?: Record<string, unknown> }>>(
      pendingUpdates,
      [],
    );
    const states = parseJson<Record<string, unknown>>(canonStates, {});
    for (const update of updates) {
      if (!update.character_id || !update.changes) continue;
      const current = typeof states[update.character_id] === "object" ? states[update.character_id] : {};
      states[update.character_id] = { ...(current as object), ...update.changes };
    }
    const updated = await api<CanonState>(`/novels/${novel.id}/canon-state`, {
      method: "PATCH",
      body: JSON.stringify({ character_states: states, pending_character_updates: [] }),
    });
    setCanon(updated);
    setCanonStates(updated.character_states_json);
    setPendingUpdates(updated.pending_character_updates_json);
    setMessage("人物状态已人工确认并写入 CanonState");
  }

  return (
    <main className="grid h-[calc(100vh-8rem)] grid-cols-[260px_minmax(480px,1fr)_350px] gap-px bg-black/10">
      <aside className="overflow-y-auto bg-[#e9e2d6] p-4">
        <details className="panel mb-4 p-4">
          <summary className="cursor-pointer font-semibold">故事总纲与约束</summary>
          <div className="mt-4 space-y-3">
            <div><label className="label">简介</label><textarea className="field min-h-20" value={novelForm.synopsis} onChange={(e) => setNovelForm({ ...novelForm, synopsis: e.target.value })} /></div>
            <div><label className="label">故事总纲</label><textarea className="field min-h-40" value={novelForm.story_outline} onChange={(e) => setNovelForm({ ...novelForm, story_outline: e.target.value })} /></div>
            <div><label className="label">写作风格</label><textarea className="field min-h-20" value={novelForm.style_guide} onChange={(e) => setNovelForm({ ...novelForm, style_guide: e.target.value })} /></div>
            <div><label className="label">禁止事项</label><textarea className="field min-h-20" value={novelForm.forbidden_content} onChange={(e) => setNovelForm({ ...novelForm, forbidden_content: e.target.value })} /></div>
            <button className="btn-primary w-full" onClick={() => void saveNovel()}>保存总纲</button>
          </div>
        </details>

        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-serif text-xl font-semibold">章节树</h2>
          <button className="btn-soft px-2 py-1" onClick={() => void addChapter()}>+</button>
        </div>
        <div className="space-y-2">
          {chapters.map((chapter) => (
            <button
              key={chapter.id}
              className={`w-full rounded-xl border p-3 text-left transition ${
                selectedId === chapter.id ? "border-moss bg-white shadow-sm" : "border-black/10 bg-white/45 hover:bg-white/70"
              }`}
              onClick={() => setSelectedId(chapter.id)}
            >
              <div className="text-[10px] font-bold uppercase tracking-wider text-black/35">Chapter {chapter.order_index}</div>
              <div className="mt-1 truncate font-semibold">{chapter.title}</div>
              <div className="mt-1 flex items-center justify-between text-[11px] text-black/40"><span>{chapter.status}</span><span>v{chapter.version}</span></div>
            </button>
          ))}
        </div>
      </aside>

      <section className="overflow-y-auto bg-[#f8f5ee] p-6">
        {error && <div className="mb-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</div>}
        {message && <div className="mb-4 rounded-xl bg-moss/10 p-3 text-sm text-moss">{message}</div>}
        {selected ? (
          <form onSubmit={saveChapter}>
            <div className="mb-5 flex items-center gap-3">
              <input className="w-full bg-transparent font-serif text-3xl font-semibold outline-none" value={chapterForm.title} onChange={(e) => setChapterForm({ ...chapterForm, title: e.target.value })} />
              <button className="btn-primary shrink-0">保存章节</button>
            </div>
            <div className="mb-4 grid grid-cols-2 gap-4">
              <div><label className="label">本章目标</label><textarea className="field min-h-28" value={chapterForm.goal} onChange={(e) => setChapterForm({ ...chapterForm, goal: e.target.value })} /></div>
              <div><label className="label">章节大纲</label><textarea className="field min-h-28" value={chapterForm.outline} onChange={(e) => setChapterForm({ ...chapterForm, outline: e.target.value })} /></div>
            </div>
            <div className="mb-4">
              <label className="label">本章相关角色</label>
              <div className="flex flex-wrap gap-2">
                {characters.map((character) => {
                  const checked = chapterForm.characterIds.includes(character.id);
                  return (
                    <label key={character.id} className={`cursor-pointer rounded-full border px-3 py-1 text-xs ${checked ? "border-moss bg-moss text-white" : "border-black/10 bg-white"}`}>
                      <input
                        className="hidden"
                        type="checkbox"
                        checked={checked}
                        onChange={() => setChapterForm({
                          ...chapterForm,
                          characterIds: checked
                            ? chapterForm.characterIds.filter((id) => id !== character.id)
                            : [...chapterForm.characterIds, character.id],
                        })}
                      />
                      {character.name}
                    </label>
                  );
                })}
                {characters.length === 0 && <span className="text-xs text-black/40">请先在“角色卡”中创建人物</span>}
              </div>
            </div>
            <label className="label">章节正文 · 可直接人工编辑</label>
            <textarea
              className="field min-h-[520px] bg-white px-5 py-4 font-serif text-base leading-8"
              value={chapterForm.content}
              onChange={(e) => setChapterForm({ ...chapterForm, content: e.target.value })}
              placeholder="在这里写作，或从右侧调用本地模型生成..."
            />
            {selected.summary && (
              <div className="mt-4 rounded-xl border border-black/10 bg-white/60 p-4">
                <div className="label">章节摘要</div>
                <p className="text-sm leading-6 text-black/65">{selected.summary}</p>
              </div>
            )}
          </form>
        ) : (
          <div className="grid h-full place-items-center text-black/40">创建章节后开始写作</div>
        )}
      </section>

      <aside className="overflow-y-auto bg-[#eee8dc] p-4">
        <section className="panel mb-4 p-4">
          <h2 className="font-serif text-xl font-semibold">生成面板</h2>
          <label className="label mt-4">模型 Provider</label>
          <select className="field mb-3" value={providerId} onChange={(e) => setProviderId(e.target.value)}>
            <option value="">选择模型服务</option>
            {providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.name} · {provider.model}</option>)}
          </select>
          <label className="label">上下文预算</label>
          <input className="field mb-3" type="number" min={512} value={budget} onChange={(e) => setBudget(Number(e.target.value))} />
          <div className="grid grid-cols-2 gap-2">
            <button className="btn-primary" disabled={!selected || !providerId || task?.status === "running"} onClick={() => void runOperation("generate")}>生成章节</button>
            <button className="btn-soft" disabled={!selected || !providerId} onClick={() => void runOperation("summarize")}>重新摘要</button>
            <button className="btn-soft" disabled={!selected || !providerId} onClick={() => void runOperation("review")}>基础审稿</button>
            <button className="btn-soft" disabled={!selected || !providerId} onClick={() => void runOperation("character-state-update")}>人物状态</button>
          </div>
          {task && (
            <div className="mt-4 rounded-xl bg-black/5 p-3 text-xs">
              <div className="flex justify-between font-semibold"><span>{task.operation}</span><span>{task.status}</span></div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-black/10"><div className="h-full bg-moss transition-all" style={{ width: `${task.progress}%` }} /></div>
              {task.error && <p className="mt-2 text-red-700">{task.error}</p>}
              {(task.status === "pending" || task.status === "running") && (
                <button className="mt-2 text-rust" onClick={async () => setTask(await api<WritingTask>(`/writing-tasks/${task.id}/pause`, { method: "POST" }))}>暂停</button>
              )}
              {(task.status === "failed" || task.status === "paused") && (
                <button className="mt-2 text-moss" onClick={async () => {
                  const retried = await api<WritingTask>(`/writing-tasks/${task.id}/retry`, { method: "POST" });
                  setTask(retried);
                  if (selected) await waitUntilIdle(selected.id, retried);
                }}>重试</button>
              )}
            </div>
          )}
          <button className="btn-soft mt-3 w-full" disabled={!selected} onClick={() => selected && void loadChapterDetails(selected.id)}>刷新上下文与记录</button>
          <a className="btn-soft mt-2 block w-full text-center" href={`/api/novels/${novel.id}/export/markdown`}>导出 Markdown</a>
        </section>

        <details className="panel mb-4 p-4" open>
          <summary className="cursor-pointer font-semibold">上下文预览</summary>
          {context && (
            <div className="mt-3">
              <div className="mb-2 text-xs text-black/45">估算 {context.estimated_tokens} / {context.budget} tokens</div>
              <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-xl bg-ink p-3 text-[11px] leading-5 text-white/75">{context.rendered_context}</pre>
            </div>
          )}
        </details>

        <details className="panel mb-4 p-4">
          <summary className="cursor-pointer font-semibold">Canon 人物状态</summary>
          <label className="label mt-3">已确认状态 JSON</label>
          <textarea className="field min-h-32 font-mono text-[11px]" value={canonStates} onChange={(e) => setCanonStates(e.target.value)} />
          <label className="label mt-3">待确认建议 JSON</label>
          <textarea className="field min-h-32 font-mono text-[11px]" value={pendingUpdates} onChange={(e) => setPendingUpdates(e.target.value)} />
          <div className="mt-2 grid grid-cols-2 gap-2">
            <button className="btn-soft" onClick={async () => {
              const updated = await api<CanonState>(`/novels/${novel.id}/canon-state`, {
                method: "PATCH",
                body: JSON.stringify({
                  character_states: parseJson(canonStates, {}),
                  pending_character_updates: parseJson(pendingUpdates, []),
                }),
              });
              setCanon(updated);
              setMessage("CanonState 已保存");
            }}>仅保存编辑</button>
            <button className="btn-primary" disabled={!canon || parseJson<unknown[]>(pendingUpdates, []).length === 0} onClick={() => void applyPendingCharacterUpdates()}>确认并合并</button>
          </div>
        </details>

        <details className="panel mb-4 p-4">
          <summary className="cursor-pointer font-semibold">审稿建议 ({reviews.length})</summary>
          <div className="mt-3 space-y-3">
            {reviews.map((review) => (
              <article key={review.id} className="rounded-xl border border-black/10 bg-white/60 p-3 text-xs leading-5">
                <div className="mb-2 font-bold">评分 {review.score ?? "未解析"}</div>
                <p><b>目标：</b>{review.goal_alignment}</p>
                <p><b>人物：</b>{review.character_consistency}</p>
                <p><b>时间线：</b>{review.timeline_consistency}</p>
                <p><b>建议：</b>{parseJson<string[]>(review.suggestions_json, []).join("；")}</p>
              </article>
            ))}
          </div>
        </details>

        <details className="panel p-4">
          <summary className="cursor-pointer font-semibold">Generation Runs ({runs.length})</summary>
          <div className="mt-3 space-y-3">
            {runs.map((run) => (
              <details key={run.id} className="rounded-xl border border-black/10 bg-white/60 p-3 text-xs">
                <summary className="cursor-pointer"><b>{run.prompt_template_key}</b> · {run.status} · {run.duration_ms ?? "-"} ms</summary>
                <div className="label mt-3">Prompt</div>
                <pre className="max-h-52 overflow-auto whitespace-pre-wrap rounded-lg bg-black/5 p-2 text-[10px] leading-4">{run.prompt}</pre>
                <div className="label mt-3">Response</div>
                <pre className="max-h-52 overflow-auto whitespace-pre-wrap rounded-lg bg-black/5 p-2 text-[10px] leading-4">{run.response || run.error}</pre>
              </details>
            ))}
          </div>
        </details>
      </aside>
    </main>
  );
}
