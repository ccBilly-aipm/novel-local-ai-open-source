import { useMemo, useState } from "react";
import { api } from "../services/api";
import type { LocalModelInfo, LocalModelInventory } from "../types";

interface Props {
  inventory: LocalModelInventory | null;
  loading: boolean;
  error: string;
  onRefresh: () => void;
  onConfigure: (model: LocalModelInfo) => void;
}

const badgeClasses: Record<string, string> = {
  primary: "bg-rust text-white",
  secondary: "bg-moss text-white",
  test: "bg-amber-100 text-amber-800",
  candidate: "bg-slate-100 text-slate-700",
  auxiliary: "bg-violet-100 text-violet-700",
  unavailable: "bg-red-100 text-red-700",
};

const stateLabels: Record<string, string> = {
  running: "正在运行",
  installed: "已安装",
  incomplete: "未完成",
};

export default function LocalModelCenter({
  inventory,
  loading,
  error,
  onRefresh,
  onConfigure,
}: Props) {
  const current = inventory?.current_model;
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("all");
  const [level, setLevel] = useState("all");
  const [actionModel, setActionModel] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const sources = useMemo(
    () => Array.from(new Set((inventory?.models || []).map((model) => model.source))).sort(),
    [inventory],
  );
  const visibleModels = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return (inventory?.models || []).filter((model) => {
      if (source !== "all" && model.source !== source) return false;
      if (level !== "all" && model.recommendation.level !== level) return false;
      if (!normalized) return true;
      return `${model.name} ${model.source} ${model.format} ${JSON.stringify(model.details)}`.toLowerCase().includes(normalized);
    });
  }, [inventory, level, query, source]);
  const lmStudioModels = (inventory?.models || []).filter((model) => model.source === "LM Studio");
  const balancedLmStudio = lmStudioModels.find((model) => model.name.toLowerCase().includes("27b"));
  const strongestLmStudio = lmStudioModels.find((model) => model.recommendation.level === "primary");

  async function lmStudioAction(model: LocalModelInfo, action: "load" | "unload") {
    setActionModel(model.id);
    setActionMessage(`${action === "load" ? "正在加载" : "正在卸载"} ${model.name}...`);
    try {
      const result = await api<{ ok: boolean; message: string; output: string }>(
        `/model-providers/lm-studio/models/${action}`,
        {
          method: "POST",
          body: JSON.stringify({
            model_key: model.name,
            identifier: model.name,
            context_length: Number(model.details.recommended_context_length || 16384),
          }),
        },
      );
      setActionMessage(`${result.ok ? "成功" : "失败"}：${result.output || result.message}`);
      onRefresh();
    } catch (reason) {
      setActionMessage(reason instanceof Error ? reason.message : "LM Studio 操作失败");
    } finally {
      setActionModel("");
    }
  }

  return (
    <section className="panel col-span-2 overflow-hidden">
      <div className="border-b border-black/10 bg-ink px-6 py-5 text-white">
        <div className="flex items-start justify-between gap-6">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-white/45">
              Local model center
            </div>
            <h2 className="mt-1 font-serif text-3xl font-semibold">本地模型中心</h2>
            <p className="mt-2 text-sm text-white/55">
              自动扫描 GGUF、Ollama、MLX 与 Hugging Face 缓存，区分生成、辅助和未完成模型。
            </p>
          </div>
          <button className="rounded-xl border border-white/15 px-3 py-2 text-sm hover:bg-white/10" onClick={onRefresh}>
            {loading ? "扫描中..." : "重新扫描"}
          </button>
        </div>

        {inventory && (
          <div className="mt-5 grid grid-cols-4 gap-3">
            <Metric label="本机" value={`${inventory.hardware.chip || "Apple Silicon"} · ${inventory.hardware.memory_gb || "?"}GB`} />
            <Metric label="发现模型" value={`${inventory.summary.total || 0} 个`} />
            <Metric label="当前运行" value={current?.name || "无"} />
            <Metric label="推荐主模型" value={inventory.summary.recommended_primary || "待安装"} />
          </div>
        )}
      </div>

      <div className="border-b border-black/10 bg-amber-50/60 px-6 py-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-rust px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-white">内置推荐</span>
          <h3 className="font-serif text-xl font-semibold">运行时引擎：拆解 / 频繁切换模型 → 优先 oMLX</h3>
        </div>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-black/60">
          拆解人物 / 时间线这类任务＝反复读长文 + 多次调用，还要在 Writer / Checker 之间来回切换。
          oMLX（基于 Apple 原生 MLX-engine）把多个模型常驻、用 LRU 自动换出，并支持按 API 程序化加载 / 卸载，切换不必每次冷启动、吞吐更稳，更适合这类自动化流水线；
          LM Studio 偏图形界面、GGUF 生态广、可视化调参，更适合手动单模型写作与试参。本机已内置 oMLX 接入预设，可直接选用。
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <div className="rounded-2xl border border-rust/25 bg-white/70 p-4">
            <div className="text-xs font-bold uppercase tracking-wider text-rust">oMLX · 更适合</div>
            <ul className="mt-2 space-y-1 text-xs leading-5 text-black/60">
              <li>· 拆解 / Map-Reduce 反复调用、长文频繁读取</li>
              <li>· Writer + Checker 双模型常驻、来回切换</li>
              <li>· 自动化 / headless 流水线、程序化 load·unload</li>
              <li>· MLX 量化：加载快、统一内存占用低</li>
            </ul>
          </div>
          <div className="rounded-2xl border border-moss/25 bg-white/70 p-4">
            <div className="text-xs font-bold uppercase tracking-wider text-moss">LM Studio · 更适合</div>
            <ul className="mt-2 space-y-1 text-xs leading-5 text-black/60">
              <li>· 手动单模型写作、逐章慢调</li>
              <li>· GGUF 生态、模型发现与下载</li>
              <li>· 图形界面可视化调参、并排比对</li>
              <li>· 不想碰命令行时零门槛上手</li>
            </ul>
          </div>
        </div>
        <p className="mt-3 text-[11px] leading-5 text-black/45">
          接入方式：上方「模型配置 → 运行时类型」选择 <b>oMLX</b>（默认 <code>127.0.0.1:8000/v1</code>），保存后测试连接即可；本机已安装 oMLX 时，Loop 在服务未启动会尝试自动拉起。
          结论来自既有资料与本机实测对比（当前会话联网搜索工具配置异常，未做在线复核）。
        </p>
      </div>

      {error && <div className="border-b border-red-200 bg-red-50 px-6 py-3 text-sm text-red-700">{error}</div>}

      {inventory && (
        <div className="p-6">
          <div className="mb-6 grid grid-cols-[1.1fr_0.9fr] gap-5">
            <div className="rounded-2xl border border-rust/25 bg-rust/5 p-5">
              <div className="text-xs font-bold uppercase tracking-widest text-rust">当前实际使用</div>
              {current ? (
                <>
                  <div className="mt-2 flex items-center gap-2">
                    <h3 className="font-serif text-2xl font-semibold">{current.name}</h3>
                    <span className="rounded-full bg-green-100 px-2 py-1 text-[10px] font-bold text-green-700">运行中</span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-black/60">{current.recommendation.reason}</p>
                  <div className="mt-3 text-xs text-black/45">
                    {current.source} · {current.format} · {current.size_label} · {current.path}
                  </div>
                </>
              ) : (
                <p className="mt-2 text-sm text-black/55">没有检测到正在运行的本地生成模型。</p>
              )}
            </div>
            <div className="rounded-2xl border border-moss/20 bg-moss/5 p-5">
              <div className="text-xs font-bold uppercase tracking-widest text-moss">本机推荐结论</div>
              <h3 className="mt-2 font-serif text-2xl font-semibold">
                日常写作先试 {balancedLmStudio?.name || inventory.summary.recommended_primary || "27B Q4/Q5"}
              </h3>
              <p className="mt-2 text-sm leading-6 text-black/60">
                64GB 统一内存更适合把 27B Q4/Q5 作为日常主力；{strongestLmStudio?.name || "35B-A3B/40B"}
                可用于复杂框架和审稿。当前 0.5B Coder 只保留做连接测试。精选微调模型名称不能代表实际小说质量，
                应使用同一大纲生成 2-3 个版本后再决定。
              </p>
            </div>
          </div>

          <div className="mb-4 flex items-end justify-between gap-4">
            <div>
              <h3 className="font-serif text-xl font-semibold">已发现模型</h3>
              <p className="text-xs text-black/45">
                {inventory.summary.generative || 0} 个生成模型 · {inventory.summary.auxiliary || 0} 个辅助模型 ·{" "}
                {inventory.summary.incomplete || 0} 个未完成
              </p>
            </div>
            <span className="text-xs text-black/35">
              更新于 {new Date(inventory.scanned_at).toLocaleTimeString()}
            </span>
          </div>

          <div className="mb-4 grid grid-cols-[1fr_220px_220px] gap-3 rounded-2xl border border-black/10 bg-black/[0.025] p-4">
            <div>
              <label className="label">搜索模型</label>
              <input className="field" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="名称、架构、量化，例如 qwen、Q4、MLX" />
            </div>
            <div>
              <label className="label">来源 / 服务</label>
              <select className="field" value={source} onChange={(event) => setSource(event.target.value)}>
                <option value="all">全部来源</option>
                {sources.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </div>
            <div>
              <label className="label">推荐用途</label>
              <select className="field" value={level} onChange={(event) => setLevel(event.target.value)}>
                <option value="all">全部用途</option>
                <option value="primary">主模型</option>
                <option value="secondary">均衡 / 副模型</option>
                <option value="test">联调模型</option>
                <option value="auxiliary">辅助模型</option>
                <option value="unavailable">未完成</option>
              </select>
            </div>
          </div>
          <div className="mb-3 flex items-center justify-between text-xs text-black/45">
            <span>当前筛选显示 {visibleModels.length} / {inventory.models.length} 个</span>
            <span>LM Studio 模型需要先加载，再创建 1234/v1 配置供内容页选择。</span>
          </div>
          {actionMessage && <div className="mb-4 max-h-28 overflow-auto rounded-xl bg-moss/10 px-4 py-3 text-xs leading-5 text-moss">{actionMessage}</div>}

          <div className="grid grid-cols-2 gap-3">
            {visibleModels.map((model) => (
              <article
                key={model.id}
                className={`rounded-2xl border p-4 ${
                  model.current ? "border-rust bg-rust/5" : "border-black/10 bg-white/55"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="truncate font-semibold">{model.name}</h4>
                      {model.current && <span className="rounded-full bg-green-100 px-2 py-0.5 text-[10px] font-bold text-green-700">当前</span>}
                    </div>
                    <div className="mt-1 text-xs text-black/40">
                      {model.source} · {model.format} · {model.size_label} · {stateLabels[model.state] || model.state}
                    </div>
                    {Boolean(model.details.parameters || model.details.quantization || model.details.max_context_length) && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {Boolean(model.details.parameters) && <span className="rounded bg-black/5 px-2 py-1 text-[10px]">{String(model.details.parameters)}</span>}
                        {Boolean(model.details.quantization) && <span className="rounded bg-black/5 px-2 py-1 text-[10px]">{String(model.details.quantization)}</span>}
                        {Boolean(model.details.architecture) && <span className="rounded bg-black/5 px-2 py-1 text-[10px]">{String(model.details.architecture)}</span>}
                    {Boolean(model.details.max_context_length) && <span className="rounded bg-black/5 px-2 py-1 text-[10px]">最大 {Number(model.details.max_context_length).toLocaleString()} ctx</span>}
                    {Boolean(model.details.runtime_memory_gb_estimate) && <span className="rounded bg-black/5 px-2 py-1 text-[10px]">运行约 {String(model.details.runtime_memory_gb_estimate)}</span>}
                    {Boolean(model.details.recommended_context_length) && <span className="rounded bg-black/5 px-2 py-1 text-[10px]">推荐 {Number(model.details.recommended_context_length).toLocaleString()} ctx</span>}
                      </div>
                    )}
                  </div>
                  <span className={`shrink-0 rounded-full px-2 py-1 text-[10px] font-bold ${badgeClasses[model.recommendation.level] || badgeClasses.candidate}`}>
                    {model.recommendation.label}
                  </span>
                </div>
                <p className="mt-3 text-sm leading-5 text-black/60">{model.recommendation.reason}</p>
                {model.recommendation.tasks.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1">
                    {model.recommendation.tasks.map((task) => (
                      <span key={task} className="rounded-full bg-black/5 px-2 py-1 text-[10px] text-black/55">{task}</span>
                    ))}
                  </div>
                )}
                <div className="mt-3 rounded-xl bg-black/[0.035] p-3 text-xs leading-5 text-black/55">
                  <b>怎么用：</b>{model.recommendation.setup}
                </div>
                <div className="mt-2 text-[11px] leading-5 text-black/45">
                  <b>内存说明：</b>{String(model.details.runtime_memory_note || "运行内存受上下文与并发影响。")}
                  {Boolean(model.details.defaults_source) && <><br /><b>参数来源：</b>{String(model.details.defaults_source)}</>}
                  {Boolean(model.details.model_card_url) && (
                    <><br /><a className="font-semibold text-moss underline" href={String(model.details.model_card_url)} target="_blank" rel="noreferrer">查看 Hugging Face 模型卡</a></>
                  )}
                </div>
                {Object.keys(model.recommendation.options).length > 0 && (
                  <div className="mt-3">
                    <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-black/40">推荐默认参数</div>
                    <code className="block max-h-32 overflow-auto rounded-xl bg-ink p-3 text-[10px] leading-4 text-white/70">
                      {JSON.stringify(model.recommendation.options, null, 2)}
                    </code>
                  </div>
                )}
                <div className="mt-3 grid grid-cols-2 gap-2">
                  {model.source === "LM Studio" && (
                    <button
                      className="btn-soft"
                      disabled={actionModel === model.id}
                      onClick={() => void lmStudioAction(model, model.current ? "unload" : "load")}
                    >
                      {actionModel === model.id ? "处理中..." : model.current ? "从内存卸载" : "加载到 LM Studio"}
                    </button>
                  )}
                  {model.provider_template && (
                    <button className="btn-primary" onClick={() => onConfigure(model)}>
                      选为可用配置
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>

          <div className="mt-6">
            <h3 className="mb-3 font-serif text-xl font-semibold">推荐使用方式</h3>
            <div className="grid grid-cols-3 gap-3">
              {inventory.usage_profiles.map((profile) => (
                <article key={profile.name} className="rounded-2xl border border-black/10 bg-white/55 p-4">
                  <div className="text-xs font-bold uppercase tracking-wider text-rust">{profile.name}</div>
                  <div className="mt-2 font-semibold">{profile.model}</div>
                  <p className="mt-2 text-xs leading-5 text-black/50">{profile.why}</p>
                  <code className="mt-3 block rounded-lg bg-ink p-2 text-[10px] leading-4 text-white/70">{profile.settings}</code>
                </article>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-white/[0.07] p-3">
      <div className="text-[10px] uppercase tracking-wider text-white/40">{label}</div>
      <div className="mt-1 truncate text-sm font-semibold">{value}</div>
    </div>
  );
}
