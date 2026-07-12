import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, parseJson } from "../../services/api";
import type {
  Chapter,
  ChapterLoopRun,
  ChapterLoopRunSummary,
  Character,
  ContextPreview,
  ModelProvider,
  MultiChapterRun,
  Novel,
  ReferenceSearchItem,
  ReferenceSelection,
  ReviewMode,
  WorldRule,
} from "../../types";
import ContextInspector from "./ContextInspector";
import CurrentRunCard from "./CurrentRunCard";
import { recommendProvider } from "../../utils/modelDisplay";

interface Props {
  projectId: string;
  novel: Novel;
  providers: ModelProvider[];
  runs: ChapterLoopRunSummary[];
  onOpenRun: (runId: string) => void;
  onRunsChanged: () => Promise<void>;
}

const WRITER_PROVIDER_KEY = "novel-local-ai.writer-provider-id";
const CHECKER_PROVIDER_KEY = "novel-local-ai.checker-provider-id";

export default function ChapterWorkspaceV2({
  projectId,
  novel,
  providers,
  runs,
  onOpenRun,
  onRunsChanged,
}: Props) {
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [rules, setRules] = useState<WorldRule[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState({ title: "", goal: "", outline: "", content: "", characterIds: [] as string[] });
  const [providerId, setProviderId] = useState("");
  const [writerProviderId, setWriterProviderId] = useState("");
  const [checkerProviderId, setCheckerProviderId] = useState("");
  const [budget, setBudget] = useState(24000);
  const [maxOutputTokens, setMaxOutputTokens] = useState(8192);
  const [reviewMode, setReviewMode] = useState<ReviewMode>("ai_auto_commit");
  const [chapterCount, setChapterCount] = useState(1);
  const [maxRevisionRounds, setMaxRevisionRounds] = useState(3);
  const [referenceQuery, setReferenceQuery] = useState("");
  const [referenceResults, setReferenceResults] = useState<ReferenceSearchItem[]>([]);
  const [references, setReferences] = useState<ReferenceSelection[]>([]);
  const [context, setContext] = useState<ContextPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const selected = useMemo(() => chapters.find((chapter) => chapter.id === selectedId) || null, [chapters, selectedId]);
  const chapterRuns = useMemo(
    () => runs.filter((run) => run.chapter_id === selectedId),
    [runs, selectedId],
  );
  const currentRun = chapterRuns.find((run) => run.active_slot === 1)
    || null;

  async function load() {
    const [chapterData, characterData, ruleData] = await Promise.all([
      api<Chapter[]>(`/novels/${novel.id}/chapters`),
      api<Character[]>(`/novels/${novel.id}/characters`),
      api<WorldRule[]>(`/novels/${novel.id}/world-rules`),
    ]);
    setChapters(chapterData);
    setCharacters(characterData);
    setRules(ruleData);
    if (!selectedId && chapterData.length) {
      setSelectedId(chapterData.find((chapter) => !chapter.content.trim())?.id || chapterData[chapterData.length - 1].id);
    }
  }

  useEffect(() => {
    void load().catch((reason) => setError(reason instanceof Error ? reason.message : "章节加载失败"));
  }, [novel.id]);

  useEffect(() => {
    const enabled = providers.filter((provider) => provider.enabled);
    if (enabled.length === 0) return;
    const byId = (id: string | null) => (id ? enabled.find((provider) => provider.id === id) : undefined);
    // 正文(Writer)默认大模型≈35B；Checker 默认小快模型 → 自动形成「大写小检」分工（都可手动改）。
    const writer = byId(window.localStorage.getItem(WRITER_PROVIDER_KEY))
      || byId(recommendProvider(providers, null, "writer"))
      || enabled[0];
    const checker = byId(window.localStorage.getItem(CHECKER_PROVIDER_KEY))
      || byId(recommendProvider(providers, null, "checker"));
    if (writer) setProviderId(writer.id);
    // 仅当 Checker 与正文不同才显式设置（相同则留空＝继承正文，避免冗余）。
    if (checker && writer && checker.id !== writer.id) setCheckerProviderId(checker.id);
  }, [providers]);

  useEffect(() => {
    if (!selected) return;
    setForm({
      title: selected.title,
      goal: selected.outline?.goal || "",
      outline: selected.outline?.outline_content || "",
      content: selected.content,
      characterIds: parseJson<string[]>(selected.outline?.character_ids_json || "[]", []),
    });
    void api<ContextPreview>(`/chapters/${selected.id}/context-preview?budget=${budget}`)
      .then(setContext)
      .catch(() => setContext(null));
  }, [selected?.id, selected?.updated_at, budget]);

  useEffect(() => {
    const query = referenceQuery.trim().replace(/^@/, "");
    if (!query) {
      setReferenceResults([]);
      return;
    }
    const timer = window.setTimeout(() => {
      void api<ReferenceSearchItem[]>(`/projects/${projectId}/references/search?q=${encodeURIComponent(query)}`)
        .then(setReferenceResults)
        .catch(() => setReferenceResults([]));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [projectId, referenceQuery]);

  async function addChapter() {
    const created = await api<Chapter>("/chapters", {
      method: "POST",
      body: JSON.stringify({
        novel_id: novel.id,
        title: `第 ${chapters.length + 1} 章`,
        outline: { goal: "", outline_content: "", character_ids: [] },
      }),
    });
    await load();
    setSelectedId(created.id);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    const updated = await api<Chapter>(`/chapters/${selected.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        title: form.title,
        content: form.content,
        outline: {
          goal: form.goal,
          outline_content: form.outline,
          character_ids: form.characterIds,
          required_plot_points: parseJson(selected.outline?.required_plot_points_json || "[]", []),
          location_ids: parseJson(selected.outline?.location_ids_json || "[]", []),
          style_notes: selected.outline?.style_notes || "",
        },
      }),
    });
    setChapters((items) => items.map((item) => item.id === updated.id ? updated : item));
    setMessage("正式章节已保存，后续 Loop 会使用这份内容。");
  }

  async function startLoop() {
    if (!selected || !providerId) return;
    setBusy(true);
    setError("");
    try {
      if (!Number.isInteger(chapterCount) || chapterCount < 1) {
        throw new Error("生成章数必须是大于 0 的整数。");
      }
      if (chapterCount > 10 && !window.confirm(
        `本次将连续生成 ${chapterCount} 章，耗时、模型调用次数和一致性风险都会明显增加。\n\n仍要继续吗？`,
      )) return;
      let permissionConfirmed = false;
      if (reviewMode === "full_autonomous") {
        permissionConfirmed = window.confirm(
          `你正在开启完全自动模式，本次计划从当前章节开始连续处理 ${chapterCount} 章。\n\n`
          + "AI 将在当前项目内生成、检查、修订、写入正式正文并更新故事记忆。\n"
          + "AI 不会删除项目、章节或版本，不会修改模型配置，也不会绕过日志。\n\n"
          + "建议先从 3 章以内开始。授予本次运行权限？",
        );
        if (!permissionConfirmed) return;
      }
      window.localStorage.setItem(WRITER_PROVIDER_KEY, providerId);
      const payload = {
        provider_id: providerId,
        writer_provider_id: writerProviderId || null,
        checker_provider_id: checkerProviderId || null,
        context_budget: budget,
        options: { max_tokens: maxOutputTokens },
        mode: reviewMode,
        max_revision_rounds_per_chapter: maxRevisionRounds,
        stop_on_major_after_rounds: maxRevisionRounds,
        references: references.map(({ type, source_id, reason }) => ({ type, source_id, reason })),
        permission_confirmed: permissionConfirmed,
      };
      if (chapterCount > 1) {
        const run = await api<MultiChapterRun>(`/projects/${projectId}/multi-chapter-runs`, {
          method: "POST",
          body: JSON.stringify({
            ...payload,
            start_chapter_id: selected.id,
            chapter_count: chapterCount,
            checkpoint_every: 3,
          }),
        });
        setMessage(`多章生产线已创建：计划 ${run.chapter_count} 章。可在 Loop Runs 查看进度、暂停或恢复。`);
      } else {
        const run = await api<ChapterLoopRun>(`/projects/${projectId}/chapters/${selected.id}/auto-run`, {
          method: "POST",
          body: JSON.stringify(payload),
        });
        onOpenRun(run.id);
      }
      await onRunsChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Loop 启动失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid grid-cols-1 gap-px bg-black/10 lg:h-[calc(100vh-8.9rem)] lg:grid-cols-[230px_minmax(360px,1fr)_320px]">
      <aside className="overflow-y-auto bg-[#e9e2d6] p-4">
        <div className="mb-3 flex items-center justify-between">
          <div><div className="label">Chapters</div><h2 className="font-serif text-xl font-semibold">章节</h2></div>
          <button className="btn-soft px-3" onClick={() => void addChapter()}>+</button>
        </div>
        <div className="space-y-2">
          {chapters.map((chapter) => {
            const run = runs.find((item) => item.chapter_id === chapter.id && item.active_slot === 1);
            return (
              <button
                key={chapter.id}
                className={`w-full rounded-xl border p-3 text-left ${
                  selectedId === chapter.id ? "border-moss bg-white shadow-sm" : "border-black/10 bg-white/45 hover:bg-white/70"
                }`}
                onClick={() => setSelectedId(chapter.id)}
              >
                <div className="flex justify-between text-[10px] font-bold uppercase tracking-wider text-black/35">
                  <span>Chapter {chapter.order_index}</span><span>{run?.status || chapter.status}</span>
                </div>
                <div className="mt-1 truncate font-semibold">{chapter.title}</div>
                <div className="mt-1 text-[11px] text-black/40">{chapter.content.trim() ? `${chapter.content.length} 字符` : "仅有大纲"}</div>
              </button>
            );
          })}
          {chapters.length === 0 && <div className="rounded-xl border border-dashed border-black/15 p-5 text-center text-xs text-black/40">创建第一章后开始 Loop。</div>}
        </div>
      </aside>

      <section className="overflow-y-auto bg-[#f8f5ee] p-6">
        {error && <div className="mb-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</div>}
        {message && <div className="mb-4 rounded-xl bg-moss/10 p-3 text-sm text-moss">{message}</div>}
        {selected ? (
          <form onSubmit={save}>
            <div className="mb-3 flex items-center justify-between">
              <div>
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-moss">Published chapter content</div>
                <div className="text-xs text-black/40">这是正式正文。Run 候选版本在审批前不会覆盖这里。</div>
              </div>
              <button className="btn-primary">保存正式章节</button>
            </div>
            <input className="mb-5 w-full bg-transparent font-serif text-3xl font-semibold outline-none" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} />
            <div className="mb-4 grid grid-cols-2 gap-4">
              <div><label className="label">本章目标</label><textarea className="field min-h-28" value={form.goal} onChange={(event) => setForm({ ...form, goal: event.target.value })} /></div>
              <div><label className="label">章节大纲</label><textarea className="field min-h-28" value={form.outline} onChange={(event) => setForm({ ...form, outline: event.target.value })} /></div>
            </div>
            <label className="label">相关角色</label>
            <div className="mb-4 flex flex-wrap gap-2">
              {characters.map((character) => {
                const checked = form.characterIds.includes(character.id);
                return (
                  <button
                    key={character.id}
                    type="button"
                    className={`rounded-full border px-3 py-1 text-xs ${checked ? "border-moss bg-moss text-white" : "border-black/10 bg-white"}`}
                    onClick={() => setForm({
                      ...form,
                      characterIds: checked ? form.characterIds.filter((id) => id !== character.id) : [...form.characterIds, character.id],
                    })}
                  >
                    {character.name}
                  </button>
                );
              })}
            </div>
            <label className="label">正式正文 · 可人工编辑</label>
            <textarea
              className="field min-h-[520px] bg-white px-5 py-4 font-serif text-base leading-8"
              value={form.content}
              onChange={(event) => setForm({ ...form, content: event.target.value })}
              placeholder="人工写作，或从右侧启动单章 Loop..."
            />
          </form>
        ) : <div className="grid h-full place-items-center text-black/40">创建章节后开始写作</div>}
      </section>

      <aside className="overflow-y-auto bg-[#eee8dc] p-4">
        {selected && currentRun ? (
          <CurrentRunCard run={currentRun} onOpen={() => onOpenRun(currentRun.id)} />
        ) : (
          <section className="panel mb-4 p-4">
            <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-rust">Chapter production line</div>
            <h2 className="mt-1 font-serif text-xl font-semibold">生成候选版本</h2>
            <p className="mt-2 text-xs leading-5 text-black/45">可填写任意大于 0 的整数。每章仍生成不可变版本，并独立检查、修订和写入。</p>
            <label className="label mt-4">运行模式</label>
            <select className="field mb-2" value={reviewMode} onChange={(event) => setReviewMode(event.target.value as ReviewMode)}>
              <option value="ai_auto_commit">AI 自动修订并写入</option>
              <option value="ai_auto_revise">AI 自动修订，人工批准</option>
              <option value="ai_review_suggest">AI 审核并建议</option>
              <option value="manual_review">人工审批</option>
              <option value="full_autonomous">完全自动生产</option>
            </select>
            <p className={`mb-3 rounded-lg px-3 py-2 text-[11px] leading-5 ${
              ["ai_auto_commit", "full_autonomous"].includes(reviewMode)
                ? "bg-amber-50 text-amber-900"
                : "bg-black/[0.03] text-black/45"
            }`}>
              {reviewMode === "manual_review" && "检查后等待你 approve / reject / revise，不写入正式正文。"}
              {reviewMode === "ai_review_suggest" && "AI 只给诊断建议，仍由你决定正文。"}
              {reviewMode === "ai_auto_revise" && "AI 可生成修订版本并复检，最终仍等待你的批准。"}
              {reviewMode === "ai_auto_commit" && "通过阈值后会备份旧正文并自动写入，同时生成章节摘要。"}
              {reviewMode === "full_autonomous" && "按章自动生成、修订、写入和更新记忆；遇到 blocker 或安全上限会暂停。"}
            </p>
            <label className="label mt-4">正文模型</label>
            <select className="field mb-3" value={providerId} onChange={(event) => setProviderId(event.target.value)}>
              <option value="">选择 Provider</option>
              {providers.filter((provider) => provider.enabled).map((provider) => (
                <option key={provider.id} value={provider.id}>{provider.name} · {provider.model}</option>
              ))}
            </select>
            <details className="mb-3 rounded-lg bg-black/[0.02] px-3 py-2">
              <summary className="cursor-pointer text-[11px] leading-5 text-black/50">
                高级：Writer / Checker 分模型（默认都与正文模型相同）
              </summary>
              <label className="label mt-2">Writer 模型（写作 / 修订）</label>
              <select className="field mb-2" value={writerProviderId} onChange={(event) => setWriterProviderId(event.target.value)}>
                <option value="">与正文模型相同</option>
                {providers.filter((provider) => provider.enabled).map((provider) => (
                  <option key={provider.id} value={provider.id}>{provider.name} · {provider.model}</option>
                ))}
              </select>
              <label className="label">Checker 模型（连续性 / 状态抽取）</label>
              <select className="field" value={checkerProviderId} onChange={(event) => setCheckerProviderId(event.target.value)}>
                <option value="">与正文模型相同</option>
                {providers.filter((provider) => provider.enabled).map((provider) => (
                  <option key={provider.id} value={provider.id}>{provider.name} · {provider.model}</option>
                ))}
              </select>
              <p className="mt-2 text-[10px] leading-4 text-black/40">
                例：Writer 选 dense 大模型保文笔，Checker 选 MoE 小模型求快。仅自动模式下的检查/状态抽取生效。
              </p>
            </details>
            <label className="label">上下文预算</label>
            <input className="field" type="number" min={512} max={131072} value={budget} onChange={(event) => setBudget(Number(event.target.value))} />
            <label className="label mt-3">最大输出 tokens</label>
            <input className="field" type="number" min={256} max={32768} step={256} value={maxOutputTokens} onChange={(event) => setMaxOutputTokens(Math.max(256, Number(event.target.value) || 256))} />
            <p className="mt-1 text-[10px] leading-4 text-black/40">限制单次生成长度，避免碰到模型输出上限被截断。建议不超过模型推荐输出（多数本地模型 8192）。</p>
            <label className="label mt-3">生成章数</label>
            <input
              className="field mb-3"
              type="number"
              min={1}
              step={1}
              value={chapterCount}
              onChange={(event) => setChapterCount(Number(event.target.value))}
            />
            {chapterCount > 1 && (
              <p className="mb-3 rounded-lg bg-blue-50 px-3 py-2 text-[11px] leading-5 text-blue-900">
                从当前章节开始按章节顺序运行。缺少章节或计划时会优先从故事总纲提取并补建。
              </p>
            )}
            {["ai_auto_revise", "ai_auto_commit", "full_autonomous"].includes(reviewMode) && (
              <>
                <label className="label">每章最大自动修订轮次</label>
                <input
                  className="field mb-3"
                  type="number"
                  min={1}
                  max={10}
                  step={1}
                  value={maxRevisionRounds}
                  onChange={(event) => setMaxRevisionRounds(Math.max(1, Math.min(10, Number(event.target.value) || 1)))}
                />
              </>
            )}
            <label className="label">引用内容</label>
            <input
              className="field"
              value={referenceQuery}
              onChange={(event) => setReferenceQuery(event.target.value)}
              placeholder="@章节名或版本"
            />
            {referenceResults.length > 0 && (
              <div className="mt-1 max-h-44 overflow-y-auto rounded-xl border border-black/10 bg-white p-1 shadow-lg">
                {referenceResults.map((item) => (
                  <button
                    key={`${item.type}-${item.id}`}
                    type="button"
                    className="block w-full rounded-lg px-3 py-2 text-left hover:bg-black/[0.04]"
                    onClick={() => {
                      if (!references.some((reference) => reference.source_id === item.id)) {
                        setReferences([...references, {
                          type: item.type,
                          source_id: item.id,
                          title: item.title,
                          reason: "",
                          token_estimate: item.token_estimate,
                        }]);
                      }
                      setReferenceQuery("");
                      setReferenceResults([]);
                    }}
                  >
                    <div className="text-xs font-semibold">{item.title}</div>
                    <div className="truncate text-[10px] text-black/40">{item.subtitle}</div>
                  </button>
                ))}
              </div>
            )}
            <div className="mt-2 space-y-2">
              {references.map((reference) => (
                <div key={reference.source_id} className="rounded-xl border border-black/10 bg-white/60 p-2">
                  <div className="flex items-center justify-between gap-2 text-[11px] font-semibold">
                    <span className="truncate">@{reference.title}</span>
                    <button type="button" className="text-black/35" onClick={() => setReferences(references.filter((item) => item.source_id !== reference.source_id))}>×</button>
                  </div>
                  <input
                    className="mt-2 w-full rounded-lg border border-black/10 bg-white px-2 py-1 text-[11px]"
                    value={reference.reason}
                    onChange={(event) => setReferences(references.map((item) => item.source_id === reference.source_id ? { ...item, reason: event.target.value } : item))}
                    placeholder="参考目的，例如：参考战斗节奏"
                  />
                </div>
              ))}
            </div>
            <button className="btn-primary mt-4 w-full" disabled={!selected || !providerId || busy} onClick={() => void startLoop()}>
              {busy ? "正在创建 Run..." : chapterCount > 1 ? `启动 ${chapterCount} 章生产线` : ["ai_auto_commit", "full_autonomous"].includes(reviewMode) ? "启动自动写入 Run" : "启动单章 Loop"}
            </button>
            {!providers.some((provider) => provider.enabled) && <p className="mt-3 text-xs text-red-700">没有启用的模型配置，请先到“本地模型”。</p>}
          </section>
        )}
        {selected && <div className="mt-4"><ContextInspector chapter={selected} characters={characters} rules={rules} context={context} /></div>}
      </aside>
    </main>
  );
}
