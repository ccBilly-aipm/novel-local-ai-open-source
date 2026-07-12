import { ChangeEvent, useEffect, useState } from "react";
import { api, parseJson } from "../services/api";
import type {
  CandidateActionResult,
  DeconstructionRun,
  LocalModelInventory,
  ModelProvider,
  Novel,
  StagedCandidate,
  StoryEngineeringOperation,
} from "../types";
import { friendlyModelLabel, localModelForProvider, recommendProvider, serviceOf } from "../utils/modelDisplay";
import type { ModelService } from "../utils/modelDisplay";

type Mode = "idea" | "deconstruct" | "pastiche";

const modes: ReadonlyArray<[Mode, string, string]> = [
  ["idea", "从想法生成", "给一个想法，生成故事框架 / 人物 / 世界观 / 章节计划的结构化候选。"],
  ["deconstruct", "拆解参考小说", "上传或粘贴原文，自动分块拆解出 10 个维度的结构化候选。"],
  ["pastiche", "仿写新作", "基于已采纳的设定与你的方向，生成一部形似神似的全新原创框架。"],
];

const ideaSubOperations: ReadonlyArray<[StoryEngineeringOperation, string]> = [
  ["framework", "故事框架"],
  ["characters", "人物卡"],
  ["world_rules", "世界规则"],
  ["chapter_plan", "章节计划"],
];

const deconDimensions: ReadonlyArray<[string, string]> = [
  ["characters", "人物线"],
  ["worldbuilding", "世界观"],
  ["timeline", "时间线"],
  ["plot_threads", "情节线"],
  ["meta", "定位"],
  ["structure", "结构"],
  ["setup_payoff", "伏笔"],
  ["theme", "主题"],
  ["pov", "视角"],
  ["style_fingerprint", "文风"],
];

const candidateTypeLabels: Record<string, string> = {
  staged_framework: "故事框架",
  staged_character: "人物卡",
  staged_world_rule: "世界规则",
  staged_chapter_plan: "章节计划",
  staged_state_change: "状态推进",
  staged_decon_characters: "拆解·人物",
  staged_decon_worldbuilding: "拆解·世界观",
  staged_decon_timeline: "拆解·时间线",
  staged_decon_plot_threads: "拆解·情节线",
  staged_decon_meta: "拆解·定位",
  staged_decon_structure: "拆解·结构",
  staged_decon_setup_payoff: "拆解·伏笔",
  staged_decon_theme: "拆解·主题",
  staged_decon_pov: "拆解·视角",
  staged_decon_style_fingerprint: "拆解·文风",
};

function candidateSummary(candidate: StagedCandidate): { title: string; body: string } {
  const data = parseJson<Record<string, unknown>>(candidate.content_json, {});
  const text = (value: unknown) => (typeof value === "string" ? value : "");
  switch (candidate.record_type) {
    case "staged_framework":
      return { title: "故事框架", body: text(data.synopsis) || text(data.story_outline) };
    case "staged_character":
    case "staged_decon_characters":
      return { title: `人物 · ${text(data.name)}`, body: `${text(data.role)} ${text(data.description)}`.trim() };
    case "staged_world_rule":
    case "staged_decon_worldbuilding":
      return { title: `规则 · ${text(data.name)}`, body: text(data.description) };
    case "staged_chapter_plan":
      return { title: `章节 · ${text(data.title)}`, body: text(data.goal) || text(data.outline_content) };
    case "staged_decon_timeline":
      return { title: `事件 · ${text(data.title)}`, body: text(data.description) };
    case "staged_decon_plot_threads":
      return { title: `情节线 · ${text(data.name)}`, body: text(data.description) };
    case "staged_decon_meta":
      return { title: "定位", body: text(data.logline) || text(data.premise) || text(data.genre) };
    case "staged_decon_structure":
      return { title: `节拍 · ${text(data.name)}`, body: text(data.description) };
    case "staged_decon_setup_payoff":
      return { title: "伏笔", body: text(data.setup) };
    case "staged_decon_theme":
      return { title: `主题 · ${text(data.name)}`, body: text(data.description) };
    case "staged_decon_pov":
      return { title: "视角", body: `${text(data.person)} ${text(data.viewpoint_character)}`.trim() };
    case "staged_decon_style_fingerprint":
      return { title: "文风指纹", body: text(data.summary) };
    case "staged_state_change":
      return { title: `状态 · ${text(data.character_name)}`, body: text(data.new_state) };
    default:
      return { title: candidateTypeLabels[candidate.record_type] || candidate.record_type, body: "" };
  }
}

function confidenceOf(candidate: StagedCandidate): number {
  const meta = parseJson<Record<string, unknown>>(candidate.metadata_json, {});
  return typeof meta.confidence === "number" ? meta.confidence : 0;
}

// 三轮循环 REFINE 标注：可迁移层级（决定仿写换皮/照搬/复刻）+ 仿写可复用度。
const layerLabels: Record<string, { label: string; cls: string }> = {
  surface: { label: "表层·换皮", cls: "bg-amber-100 text-amber-700" },
  pattern: { label: "模式·照搬", cls: "bg-sky-100 text-sky-700" },
  signature: { label: "灵魂·复刻", cls: "bg-violet-100 text-violet-700" },
};

function refineOf(candidate: StagedCandidate): { layer?: string; reuseScore?: number } {
  const data = parseJson<Record<string, unknown>>(candidate.content_json, {});
  return {
    layer: typeof data.layer === "string" ? data.layer : undefined,
    reuseScore: typeof data.reuse_score === "number" ? data.reuse_score : undefined,
  };
}

function critiqueReasonOf(candidate: StagedCandidate): string {
  const meta = parseJson<Record<string, unknown>>(candidate.metadata_json, {});
  const c = meta.critique as Record<string, unknown> | undefined;
  return c && typeof c.reason === "string" ? c.reason : "";
}

interface Props {
  novel: Novel;
  onNovelChange: (novel: Novel) => void;
  onOpenChapters: () => void;
}

export default function CreativeStudio({ novel, onNovelChange, onOpenChapters }: Props) {
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [inventory, setInventory] = useState<LocalModelInventory | null>(null);
  const [providerId, setProviderId] = useState("");
  const [idea, setIdea] = useState("");
  const [referenceText, setReferenceText] = useState("");
  const [fileName, setFileName] = useState("");
  const [candidates, setCandidates] = useState<StagedCandidate[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [mode, setMode] = useState<Mode>("idea");
  const [ideaSubOp, setIdeaSubOp] = useState<StoryEngineeringOperation>("framework");
  const [deconDims, setDeconDims] = useState<string[]>(deconDimensions.map(([key]) => key));
  const [fastMode, setFastMode] = useState(true);
  const [deconRun, setDeconRun] = useState<DeconstructionRun | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  // 模型选择改为两级：先选服务（只展示 LM Studio / oMLX），再选该服务下的模型。
  const [serviceTab, setServiceTab] = useState<ModelService>("lmstudio");

  function defaultProviderForService(list: ModelProvider[]): string {
    const ok = list.find((p) => p.last_test_status === "ok");
    return (ok || list[0])?.id || "";
  }

  function pickService(svc: ModelService) {
    setServiceTab(svc);
    const list = providers.filter((p) => serviceOf(p) === svc);
    if (!list.some((p) => p.id === providerId)) setProviderId(defaultProviderForService(list));
  }

  async function load() {
    await api<ModelProvider[]>("/model-providers/sync-local", { method: "POST" });
    const [providerData, inventoryData, candidateData] = await Promise.all([
      api<ModelProvider[]>("/model-providers"),
      api<LocalModelInventory>("/model-providers/local-inventory"),
      api<StagedCandidate[]>(`/novels/${novel.id}/story-engineering/candidates`),
    ]);
    const enabled = providerData.filter((item) => item.enabled);
    setProviders(enabled);
    setInventory(inventoryData);
    setCandidates(candidateData);
    if (!providerId && enabled.length > 0) {
      // 默认只在 LM Studio / oMLX 里选；想法/仿写偏 Writer 大模型（拆解的 oMLX 默认由下方 mode 副作用接管）。
      const visible = enabled.filter((p) => serviceOf(p) === "lmstudio" || serviceOf(p) === "omlx");
      const rec = recommendProvider(visible, inventoryData, "writer");
      const chosen = visible.find((p) => p.id === rec) || visible[0] || null;
      if (chosen) {
        setProviderId(chosen.id);
        setServiceTab(serviceOf(chosen) === "omlx" ? "omlx" : "lmstudio");
      }
    }
  }

  useEffect(() => {
    void load();
  }, [novel.id]);

  // 从首页「分析一篇小说」直达：自动进入拆解模式并载入上传的原文
  useEffect(() => {
    const pending = window.localStorage.getItem("pending_deconstruct_text");
    if (pending) {
      setMode("deconstruct");
      setReferenceText(pending);
      setFileName("来自上传的参考小说");
      setMessage("已载入上传的小说。维度默认全选，直接点「拆解参考小说」即可开始分析。");
      window.localStorage.removeItem("pending_deconstruct_text");
    }
  }, []);

  // 拆解（分析小说）自动默认走 oMLX + 去审核 14B（社区甜点）：进入拆解模式时切到 oMLX 并选推荐模型（可手动改）。
  useEffect(() => {
    if (mode !== "deconstruct" || providers.length === 0) return;
    setServiceTab("omlx");
    const omlx = providers.filter((p) => serviceOf(p) === "omlx");
    if (!omlx.some((p) => p.id === providerId)) {
      setProviderId(recommendProvider(providers, inventory, "deconstruct") || defaultProviderForService(omlx));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, providers, inventory]);

  async function readFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      setMessage("单个素材文件限制为 2MB，请先拆分长文。");
      return;
    }
    setReferenceText(await file.text());
    setFileName(file.name);
    setMessage(`已载入 ${file.name}，内容只会发送给你选择的本地模型。`);
  }

  async function generateStructured() {
    if (!idea.trim() || !providerId) return;
    const operation: StoryEngineeringOperation = mode === "pastiche" ? "pastiche" : ideaSubOp;
    setBusy(true);
    setMessage("正在生成结构化候选，候选会先进入暂存，需逐条接受后才落库...");
    try {
      const created = await api<StagedCandidate[]>(`/novels/${novel.id}/story-engineering/generate`, {
        method: "POST",
        body: JSON.stringify({ provider_id: providerId, operation, idea, reference_text: referenceText }),
      });
      setCandidates((current) => [...created, ...current]);
      setMessage(`已生成 ${created.length} 条候选，请逐条检查后接受或拒绝。`);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "生成失败");
    } finally {
      setBusy(false);
    }
  }

  function pollDeconstruction(runId: string) {
    const timer = window.setInterval(async () => {
      try {
        const run = await api<DeconstructionRun>(`/novels/${novel.id}/deconstruction-runs/${runId}`);
        setDeconRun(run);
        if (run.status === "completed" || run.status === "failed") {
          window.clearInterval(timer);
          setBusy(false);
          const cands = await api<StagedCandidate[]>(`/novels/${novel.id}/story-engineering/candidates`);
          setCandidates(cands);
          setMessage(
            run.status === "completed"
              ? `拆解完成，共 ${run.candidate_count} 条候选，请逐条接受或拒绝。`
              : `拆解失败：${run.error || run.error_code}`,
          );
        }
      } catch (reason) {
        window.clearInterval(timer);
        setBusy(false);
        setMessage(reason instanceof Error ? reason.message : "拆解进度查询失败");
      }
    }, 1500);
  }

  async function generateDeconstruction() {
    const sourceText = (referenceText || idea).trim();
    if (!sourceText || !providerId || deconDims.length === 0) return;
    setBusy(true);
    setDeconRun(null);
    setMessage("正在拆解参考小说（整本分块），候选会先进入暂存，需逐条接受后才落库...");
    try {
      const run = await api<DeconstructionRun>(`/novels/${novel.id}/deconstruction-runs`, {
        method: "POST",
        body: JSON.stringify({
          provider_id: providerId,
          source_text: sourceText,
          dimensions: deconDims,
          // 并行加速：保持最稳的逐维度抽取，但并发跑多个调用（oMLX 等支持并发的后端可数倍提速）。
          options: fastMode ? { max_parallel: 3 } : {},
        }),
      });
      setDeconRun(run);
      pollDeconstruction(run.id);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "拆解发起失败");
      setBusy(false);
    }
  }

  async function decideCandidate(id: string, action: "accept" | "reject" | "restore") {
    setBusy(true);
    try {
      const result = await api<CandidateActionResult>(`/story-engineering/candidates/${id}/${action}`, {
        method: "POST",
      });
      setCandidates((current) =>
        current.map((item) => (item.id === id ? { ...item, status: result.status } : item)),
      );
      if (action === "accept") {
        setMessage(`已接受并落库：${result.detail}`);
        const fresh = await api<Novel>(`/novels/${novel.id}`);
        onNovelChange(fresh);
      } else if (action === "restore") {
        setMessage("已恢复为待采纳，可重新检查后接受。");
      } else {
        setMessage("已拒绝该候选，未落库。");
      }
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  function toggleSelect(id: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectByThreshold(min: number) {
    setSelected(
      new Set(candidates.filter((c) => c.status === "staged" && confidenceOf(c) >= min).map((c) => c.id)),
    );
  }

  function selectAllStaged() {
    setSelected(new Set(candidates.filter((c) => c.status === "staged").map((c) => c.id)));
  }

  async function acceptMany(ids: string[]) {
    if (ids.length === 0) return;
    setBusy(true);
    let ok = 0;
    for (const id of ids) {
      try {
        const result = await api<CandidateActionResult>(`/story-engineering/candidates/${id}/accept`, {
          method: "POST",
        });
        setCandidates((current) => current.map((item) => (item.id === id ? { ...item, status: result.status } : item)));
        ok += 1;
      } catch {
        /* 单条失败不阻断批量 */
      }
    }
    setSelected(new Set());
    try {
      const fresh = await api<Novel>(`/novels/${novel.id}`);
      onNovelChange(fresh);
    } catch {
      /* 刷新失败不致命 */
    }
    setMessage(`已接受 ${ok}/${ids.length} 条候选。`);
    setBusy(false);
  }

  function onGenerate() {
    if (mode === "deconstruct") return void generateDeconstruction();
    return void generateStructured();
  }

  const activeMode = modes.find(([key]) => key === mode);
  const ideaLabel =
    mode === "pastiche"
      ? "仿写方向 / 新作想法"
      : mode === "deconstruct"
        ? "参考小说原文（也可用下方上传）"
        : "你的想法、目标或设定";
  const actionLabel = mode === "deconstruct" ? "拆解参考小说" : mode === "pastiche" ? "生成仿写框架" : "生成结构化候选";
  const canGenerate =
    !busy &&
    !!providerId &&
    (mode === "deconstruct" ? deconDims.length > 0 && !!(referenceText || idea).trim() : !!idea.trim());

  return (
    <main className="mx-auto max-w-7xl p-7">
      {/* 模式选择器 */}
      <section className="mb-6">
        <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-rust">Pre-production</div>
        <h1 className="mt-1 font-serif text-3xl font-semibold">创作中心 · 前置物料</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-black/55">
          所有生成都产出<strong>可逐条采纳的候选</strong>，接受后才写入正式的故事设定 / 人物 / 世界规则 / 章节，
          绝不直接进入正文或 Canon。先选一种方式：
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          {modes.map(([key, label]) => (
            <button
              key={key}
              className={`rounded-xl border px-4 py-2.5 text-sm font-semibold transition ${
                mode === key ? "border-rust bg-rust/5 text-rust" : "border-black/10 bg-white/50 hover:bg-white"
              }`}
              onClick={() => setMode(key)}
            >
              {label}
            </button>
          ))}
        </div>
        {activeMode && <p className="mt-2 text-xs leading-5 text-black/45">{activeMode[2]}</p>}
      </section>

      <section className="mb-6 grid grid-cols-[1.35fr_0.65fr] gap-6">
        {/* 输入区 */}
        <div className="panel p-6">
          <label className="label">{ideaLabel}</label>
          <textarea
            className="field min-h-40 bg-white p-4 text-base leading-7"
            value={idea}
            onChange={(event) => setIdea(event.target.value)}
            placeholder={
              mode === "deconstruct"
                ? "把参考小说原文粘贴到这里，或用下方上传 .txt/.md。整本会自动分块拆解。"
                : mode === "pastiche"
                  ? "例如：保留参考的冷峻文风与三幕结构，写一个关于声音的悬疑新故事。"
                  : "例如：一个负责删除他人记忆的档案员，发现自己的童年也被修改过。"
            }
          />

          <div className="mt-4 rounded-xl border border-dashed border-black/15 bg-black/[0.02] p-4">
            <div className="flex items-center justify-between gap-4">
              <div>
                <div className="font-semibold">上传参考内容{mode === "deconstruct" ? "（拆解原文来源）" : "（可选）"}</div>
                <p className="mt-1 text-xs text-black/45">支持 .txt、.md；拆解模式下这就是被拆的原文。</p>
              </div>
              <label className="btn-soft cursor-pointer">
                选择文件
                <input className="hidden" type="file" accept=".txt,.md,text/plain,text/markdown" onChange={(event) => void readFile(event)} />
              </label>
            </div>
            {fileName && (
              <div className="mt-3 flex items-center justify-between rounded-lg bg-white/70 px-3 py-2 text-xs">
                <span>{fileName} · {referenceText.length.toLocaleString()} 字符</span>
                <button className="text-red-700" onClick={() => { setFileName(""); setReferenceText(""); }}>移除</button>
              </div>
            )}
          </div>

          <div className="mt-5">
            <label className="label">本次使用模型</label>
            {/* 第一级：选服务（只展示 LM Studio / oMLX） */}
            <div className="mt-1 flex gap-2">
              {([["lmstudio", "LM Studio"], ["omlx", "oMLX"]] as [ModelService, string][]).map(([svc, lbl]) => {
                const count = providers.filter((p) => serviceOf(p) === svc).length;
                return (
                  <button
                    key={svc}
                    type="button"
                    className={`flex-1 rounded-lg border px-3 py-2 text-sm ${
                      serviceTab === svc ? "border-rust bg-rust/5 font-semibold" : "border-black/10 bg-white/50 hover:bg-white"
                    }`}
                    onClick={() => pickService(svc)}
                  >
                    {lbl} <span className="text-[10px] text-black/40">({count})</span>
                  </button>
                );
              })}
            </div>
            {/* 第二级：选该服务下的模型（友好命名） */}
            <select
              className="field mt-2"
              value={providers.some((p) => p.id === providerId && serviceOf(p) === serviceTab) ? providerId : ""}
              onChange={(event) => setProviderId(event.target.value)}
            >
              <option value="">
                {providers.some((p) => serviceOf(p) === serviceTab)
                  ? `选择 ${serviceTab === "omlx" ? "oMLX" : "LM Studio"} 模型`
                  : `${serviceTab === "omlx" ? "oMLX" : "LM Studio"} 暂无已配置模型`}
              </option>
              {providers
                .filter((p) => serviceOf(p) === serviceTab)
                .map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {friendlyModelLabel(provider, inventory)}
                  </option>
                ))}
            </select>
            {/* 推荐提示：随流程变 */}
            <p className="mt-1.5 text-[11px] leading-5 text-black/45">
              {mode === "deconstruct"
                ? "📌 拆解 / 分析推荐 oMLX + 去审核模型：露骨内容不拒答、可并发更快、JSON 抽取更稳。"
                : mode === "pastiche"
                  ? "📌 仿写推荐 Writer 类模型（如 Opus-Distilled 27B），文风与结构承载更好。"
                  : "📌 从想法生成推荐能写长文的 Writer 模型；露骨题材选去审核版。"}
            </p>
            {providerId && (() => {
              const provider = providers.find((item) => item.id === providerId);
              const model = provider ? localModelForProvider(provider, inventory) : null;
              if (!provider || !model) return null;
              return (
                <div className="mt-2 rounded-lg bg-black/[0.035] px-3 py-2 text-[11px] leading-5 text-black/55">
                  <b>{String(model.details.parameters || "参数量待识别")}</b>
                  {" · "}{String(model.details.quantization || model.format)}
                  {" · 本体 "}{model.size_label}
                  {" · 推荐上下文 "}{Number(model.details.recommended_context_length || 8192).toLocaleString()}
                </div>
              );
            })()}
          </div>

          {/* 子选择：随模式 */}
          {mode === "idea" && (
            <div className="mt-5">
              <label className="label">生成什么</label>
              <div className="mt-1 flex flex-wrap gap-2">
                {ideaSubOperations.map(([key, label]) => (
                  <button
                    key={key}
                    className={`rounded-lg border px-3 py-2 text-sm ${
                      ideaSubOp === key ? "border-rust bg-rust/5" : "border-black/10 bg-white/50 hover:bg-white"
                    }`}
                    onClick={() => setIdeaSubOp(key)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}
          {mode === "deconstruct" && (
            <div className="mt-5">
              <label className="label">拆解维度（可多选）</label>
              <div className="mt-1 flex flex-wrap gap-2">
                {deconDimensions.map(([key, label]) => (
                  <button
                    key={key}
                    className={`rounded-lg border px-3 py-2 text-sm ${
                      deconDims.includes(key) ? "border-rust bg-rust/5" : "border-black/10 bg-white/50 hover:bg-white"
                    }`}
                    onClick={() =>
                      setDeconDims((cur) => (cur.includes(key) ? cur.filter((d) => d !== key) : [...cur, key]))
                    }
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {mode === "deconstruct" && (
            <label className="mt-4 flex items-start gap-2 text-sm text-black/70">
              <input className="mt-0.5" type="checkbox" checked={fastMode} onChange={(e) => setFastMode(e.target.checked)} />
              <span>并行加速（逐维度抽取 + 并发）。保持单维度小 JSON 的<b>最高可靠性</b>，靠并发跑多个调用提速；在 oMLX 等支持并发的后端上可数倍加快。关闭则严格串行。</span>
            </label>
          )}

          <button className="btn-primary mt-5 min-w-40" disabled={!canGenerate} onClick={onGenerate}>
            {busy ? "处理中..." : actionLabel}
          </button>
          {message && <div className="mt-4 rounded-xl bg-moss/10 px-4 py-3 text-sm text-moss">{message}</div>}
          {deconRun && (deconRun.status === "running" || deconRun.status === "pending") && (
            <div className="mt-4 rounded-xl bg-blue-50 px-4 py-3 text-xs text-blue-900">
              拆解中 · {deconRun.current_dimension || "准备中"} · {deconRun.processed_units}/
              {deconRun.total_units || "?"} · 已产出 {deconRun.candidate_count} 条候选
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-black/10">
                <div
                  className="h-full bg-moss transition-all"
                  style={{
                    width: `${deconRun.total_units ? Math.round((deconRun.processed_units / deconRun.total_units) * 100) : 5}%`,
                  }}
                />
              </div>
            </div>
          )}
        </div>

        {/* 侧栏 */}
        <aside className="space-y-4">
          <section className="panel p-5">
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-rust">Current project</div>
            <h2 className="mt-1 font-serif text-2xl font-semibold">{novel.title}</h2>
            <p className="mt-2 text-sm leading-6 text-black/50">{novel.synopsis || "尚未填写简介"}</p>
            <div className="mt-4 rounded-xl bg-black/[0.035] p-3 text-xs leading-5 text-black/55">
              推荐流程：从想法生成 或 拆解参考小说 → 逐条采纳前置物料 → 仿写新作（可选）→ 去章节工作区启动多章生产线。
            </div>
          </section>
        </aside>
      </section>

      {/* 统一候选区 */}
      <section className="panel p-6">
        <div className="mb-4">
          <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-rust">Candidates</div>
          <h2 className="mt-1 font-serif text-2xl font-semibold">候选 · 待采纳</h2>
          <p className="mt-1 text-xs leading-5 text-black/45">接受才写入正式资料，拒绝则丢弃。绝不直接进入正文或 Canon。已按置信度从高到低排序。</p>
        </div>
        {candidates.some((c) => c.status === "staged") && (
          <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xl bg-black/[0.03] px-3 py-2 text-xs">
            <span className="text-black/50">已选 {selected.size}</span>
            <button className="rounded-md border border-black/10 bg-white/60 px-2 py-1 hover:bg-white" onClick={selectAllStaged}>全选</button>
            <button className="rounded-md border border-black/10 bg-white/60 px-2 py-1 hover:bg-white" onClick={() => setSelected(new Set())}>清空</button>
            <span className="text-black/25">|</span>
            <span className="text-black/45">按置信度选</span>
            <button className="rounded-md border border-black/10 bg-white/60 px-2 py-1 hover:bg-white" onClick={() => selectByThreshold(0.9)}>≥90%</button>
            <button className="rounded-md border border-black/10 bg-white/60 px-2 py-1 hover:bg-white" onClick={() => selectByThreshold(0.8)}>≥80%</button>
            <button className="rounded-md border border-black/10 bg-white/60 px-2 py-1 hover:bg-white" onClick={() => selectByThreshold(0.7)}>≥70%</button>
            <div className="ml-auto flex gap-2">
              <button className="btn-primary px-3 py-1" disabled={busy || selected.size === 0} onClick={() => void acceptMany([...selected])}>
                接受选中（{selected.size}）
              </button>
              <button className="btn-soft px-3 py-1" disabled={busy} onClick={() => void acceptMany(candidates.filter((c) => c.status === "staged").map((c) => c.id))}>
                全部接受
              </button>
            </div>
          </div>
        )}
        <div className="space-y-2">
          {candidates.length === 0 && (
            <p className="text-sm text-black/40">还没有候选。在上方选模式、填写内容后点「{actionLabel}」。</p>
          )}
          {[...candidates]
            .filter((c) => c.status !== "discarded")
            .sort((a, b) => confidenceOf(b) - confidenceOf(a))
            .map((candidate) => {
            const summary = candidateSummary(candidate);
            const meta = parseJson<Record<string, unknown>>(candidate.metadata_json, {});
            const confidence = typeof meta.confidence === "number" ? meta.confidence : null;
            const refine = refineOf(candidate);
            const layer = refine.layer ? layerLabels[refine.layer] : undefined;
            return (
              <article key={candidate.id} className="rounded-xl border border-black/10 bg-white/50 p-4">
                <div className="flex items-start justify-between gap-4">
                  {candidate.status === "staged" && (
                    <input
                      type="checkbox"
                      className="mt-1.5 h-4 w-4 shrink-0"
                      checked={selected.has(candidate.id)}
                      onChange={() => toggleSelect(candidate.id)}
                    />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-full bg-black/5 px-2 py-0.5 text-[10px] font-bold">
                        {candidateTypeLabels[candidate.record_type] || candidate.record_type}
                      </span>
                      <b className="truncate">{summary.title}</b>
                      {layer && (
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${layer.cls}`}>
                          {layer.label}
                        </span>
                      )}
                      {typeof refine.reuseScore === "number" && (
                        <span className="text-[10px] font-semibold text-moss">复用度 {refine.reuseScore}</span>
                      )}
                      {confidence !== null && (
                        <span className="text-[10px] text-black/40">置信度 {Math.round(confidence * 100)}%</span>
                      )}
                    </div>
                    {summary.body && (
                      <p className="mt-1 max-h-16 overflow-hidden text-xs leading-5 text-black/55">{summary.body}</p>
                    )}
                  </div>
                  <div className="flex shrink-0 gap-2">
                    {candidate.status === "staged" ? (
                      <>
                        <button className="btn-primary px-3" disabled={busy} onClick={() => void decideCandidate(candidate.id, "accept")}>
                          接受
                        </button>
                        <button className="btn-soft px-3" disabled={busy} onClick={() => void decideCandidate(candidate.id, "reject")}>
                          拒绝
                        </button>
                      </>
                    ) : (
                      <span
                        className={`rounded-full px-2 py-1 text-[10px] font-bold ${
                          candidate.status === "accepted" ? "bg-green-100 text-green-700" : "bg-black/10 text-black/50"
                        }`}
                      >
                        {candidate.status === "accepted" ? "已接受" : "已拒绝"}
                      </span>
                    )}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
        {candidates.some((item) => item.status === "discarded") && (
          <details className="mt-4 rounded-xl border border-amber-200/60 bg-amber-50/40 px-4 py-3">
            <summary className="cursor-pointer text-xs font-semibold text-amber-800">
              AI 审校已淘汰 {candidates.filter((c) => c.status === "discarded").length} 条（臆造/太泛/无证据，点击查看，不计入采纳）
            </summary>
            <ul className="mt-2 space-y-1">
              {candidates
                .filter((c) => c.status === "discarded")
                .map((c) => {
                  const summary = candidateSummary(c);
                  return (
                    <li key={c.id} className="flex items-start justify-between gap-3 text-xs text-black/55">
                      <span className="min-w-0 flex-1">
                        <span className="font-semibold">{summary.title}</span>
                        {critiqueReasonOf(c) && <span className="text-black/40"> — {critiqueReasonOf(c)}</span>}
                      </span>
                      <button
                        className="shrink-0 font-semibold text-moss disabled:opacity-50"
                        disabled={busy}
                        onClick={() => void decideCandidate(c.id, "restore")}
                        title="AI 误杀了？恢复为待采纳"
                      >
                        恢复
                      </button>
                    </li>
                  );
                })}
            </ul>
          </details>
        )}
        {candidates.some((item) => item.status === "accepted") && (
          <div className="mt-4 rounded-xl bg-black/[0.035] px-4 py-3 text-xs leading-5 text-black/55">
            前置物料已落库。去「章节」工作区，选起始章节、把生成章数设为大于 1、保持默认的 “AI 自动修订并写入” 模式，即可启动全自动多章生产线。
            <button className="ml-2 font-semibold text-moss" onClick={onOpenChapters}>前往章节工作区 →</button>
          </div>
        )}
      </section>
    </main>
  );
}
