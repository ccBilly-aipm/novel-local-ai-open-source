import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, parseJson } from "../services/api";
import type { LocalModelInfo, LocalModelInventory, ModelProvider, ProviderTestResult } from "../types";
import ModelRoleAssignments from "../features/models/ModelRoleAssignments";
import ProviderDiagnosticsCard from "../features/models/ProviderDiagnosticsCard";
import CheckerBenchPanel from "../features/models/CheckerBenchPanel";
import WriterBenchPanel from "../features/models/WriterBenchPanel";
import LocalModelCenter from "./LocalModelCenter";

interface ProviderForm {
  name: string;
  provider_type: string;
  base_url: string;
  model: string;
  api_key: string;
  default_options: string;
  timeout_seconds: number;
  enabled: boolean;
}

interface ProviderPreset {
  label: string;
  baseUrl: string;
  timeout: number;
  options: Record<string, unknown>;
  note: string;
}

const providerPresets: Record<string, ProviderPreset> = {
  lm_studio: {
    label: "LM Studio",
    baseUrl: "http://127.0.0.1:1234/v1",
    timeout: 900,
    options: { temperature: 0.7, top_p: 0.8, top_k: 20, max_tokens: 8192, repetition_penalty: 1, force_no_think: true },
    note: "通过 LM Studio 本地 API 调用；Qwen 思考模型可用 force_no_think 跳过冗长推理。需先加载模型。",
  },
  llama_cpp: {
    label: "llama.cpp",
    baseUrl: "http://127.0.0.1:8080/v1",
    timeout: 600,
    options: { temperature: 0.7, top_p: 0.8, top_k: 20, max_tokens: 8192, repetition_penalty: 1 },
    note: "使用 llama-server 的 OpenAI-compatible /v1 接口。",
  },
  ollama: {
    label: "Ollama",
    baseUrl: "http://127.0.0.1:11434",
    timeout: 600,
    options: { temperature: 0.7, top_p: 0.8, top_k: 20, num_ctx: 32768, num_predict: 8192, repeat_penalty: 1 },
    note: "参数会发送到 Ollama options；上下文长度使用 num_ctx。",
  },
  omlx: {
    label: "oMLX",
    baseUrl: "http://127.0.0.1:8000/v1",
    timeout: 900,
    options: { temperature: 0.7, top_p: 0.8, top_k: 20, max_tokens: 8192, chat_template_kwargs: { enable_thinking: false } },
    note: "使用本机 oMLX 多模型 OpenAI-compatible 服务；服务未启动时 Loop 会尝试自动启动。",
  },
  koboldcpp: {
    label: "KoboldCpp",
    baseUrl: "http://127.0.0.1:5001",
    timeout: 600,
    options: { temperature: 0.8, top_p: 0.95, max_tokens: 3200, rep_pen: 1.08 },
    note: "默认使用 /api/v1/generate；若 Base URL 以 /v1 结尾则走 OpenAI-compatible。",
  },
  text_generation_webui: {
    label: "text-generation-webui",
    baseUrl: "http://127.0.0.1:5000/v1",
    timeout: 600,
    options: { temperature: 0.8, top_p: 0.95, max_tokens: 3200, repetition_penalty: 1.08 },
    note: "需要在 text-generation-webui 中启用 OpenAI API 扩展。",
  },
  openai_compatible: {
    label: "OpenAI-compatible",
    baseUrl: "http://127.0.0.1:8000/v1",
    timeout: 600,
    options: { temperature: 0.8, top_p: 0.95, max_tokens: 3200 },
    note: "适合 LM Studio、LocalAI 和其他兼容 /chat/completions 的本地服务。",
  },
  cloud_openai_compatible: {
    label: "Cloud OpenAI-compatible",
    baseUrl: "https://api.openai.com/v1",
    timeout: 300,
    options: { temperature: 0.7, top_p: 0.95, max_tokens: 3200 },
    note: "仅作为可选审稿或复杂分析服务；API Key 保存在本地 SQLite。",
  },
};

const experiments = [
  {
    name: "稳定续写",
    description: "优先一致性，减少跑题，适合按大纲逐章写。",
    options: { temperature: 0.65, top_p: 0.9, max_tokens: 3000, repeat_penalty: 1.1 },
  },
  {
    name: "均衡正文",
    description: "默认推荐，兼顾叙事稳定与语言变化。",
    options: { temperature: 0.8, top_p: 0.95, max_tokens: 3200, repeat_penalty: 1.08 },
  },
  {
    name: "创意改写",
    description: "增加表达变化，适合备选版本，不建议直接写入 Canon。",
    options: { temperature: 1, top_p: 0.98, max_tokens: 3600, repeat_penalty: 1.05 },
  },
  {
    name: "摘要审稿",
    description: "低随机性，适合 JSON、摘要与一致性检查。",
    options: { temperature: 0.2, top_p: 0.85, max_tokens: 1200, repeat_penalty: 1.05 },
  },
];

const parameterGuide = [
  ["temperature", "创造性", "0.1-1.2", "低值稳定，高值更有变化；正文建议 0.65-0.9。"],
  ["top_p", "候选词范围", "0.8-1.0", "与 temperature 配合；正文通常 0.9-0.95。"],
  ["max_tokens / num_predict", "最大输出", "600-4000", "摘要 600-1200，章节正文 2500-4000。"],
  ["num_ctx", "Ollama 上下文", "4096-32768", "越大越占内存；本机建议先从 16384 测试。"],
  ["repeat_penalty", "重复惩罚", "1.0-1.2", "过高会损害自然表达；建议 1.05-1.12。"],
  ["seed", "随机种子", "整数", "固定后便于复现实验；删除该字段恢复随机。"],
];

function formFromPreset(providerType = "llama_cpp"): ProviderForm {
  const preset = providerPresets[providerType] || providerPresets.openai_compatible;
  return {
    name: `Local ${preset.label}`,
    provider_type: providerType,
    base_url: preset.baseUrl,
    model: "",
    api_key: "",
    default_options: JSON.stringify(preset.options, null, 2),
    timeout_seconds: preset.timeout,
    enabled: true,
  };
}

function formFromProvider(provider: ModelProvider): ProviderForm {
  return {
    name: provider.name,
    provider_type: provider.provider_type,
    base_url: provider.base_url,
    model: provider.model,
    api_key: provider.api_key,
    default_options: provider.default_options_json,
    timeout_seconds: provider.timeout_seconds,
    enabled: provider.enabled,
  };
}

function statusLabel(status: string) {
  if (status === "ok") return "测试通过";
  if (status === "failed") return "测试失败";
  return "尚未测试";
}

export default function ModelSettings() {
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState<ProviderForm>(() => formFromPreset());
  const [message, setMessage] = useState("");
  const [inventory, setInventory] = useState<LocalModelInventory | null>(null);
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const [inventoryError, setInventoryError] = useState("");
  const [diagnostics, setDiagnostics] = useState<ProviderTestResult | null>(null);

  const selectedProvider = useMemo(
    () => providers.find((provider) => provider.id === selectedId) || null,
    [providers, selectedId],
  );
  const preset = providerPresets[form.provider_type] || providerPresets.openai_compatible;

  async function load(selectId?: string | null) {
    const data = await api<ModelProvider[]>("/model-providers");
    setProviders(data);
    const targetId = selectId === undefined ? selectedId : selectId;
    if (targetId) {
      const target = data.find((provider) => provider.id === targetId);
      if (target) {
        setSelectedId(target.id);
        setForm(formFromProvider(target));
        return;
      }
    }
    if (selectedId && !data.some((provider) => provider.id === selectedId)) {
      setSelectedId(null);
    }
  }

  async function loadInventory() {
    setInventoryLoading(true);
    try {
      setInventory(await api<LocalModelInventory>("/model-providers/local-inventory"));
      setInventoryError("");
    } catch (reason) {
      setInventoryError(reason instanceof Error ? reason.message : "本地模型扫描失败");
    } finally {
      setInventoryLoading(false);
    }
  }

  useEffect(() => {
    void (async () => {
      await api<ModelProvider[]>("/model-providers/sync-local", { method: "POST" });
      const data = await api<ModelProvider[]>("/model-providers");
      setProviders(data);
      if (data.length > 0) {
        setSelectedId(data[0].id);
        setForm(formFromProvider(data[0]));
      }
    })();
    void loadInventory();
  }, []);

  function select(provider: ModelProvider) {
    setSelectedId(provider.id);
    setForm(formFromProvider(provider));
    setMessage("");
    setDiagnostics(null);
  }

  function startNew(providerType = "llama_cpp") {
    setSelectedId(null);
    setForm(formFromPreset(providerType));
    setMessage("填写模型名称后保存，再执行连接测试。");
    setDiagnostics(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function changeProviderType(providerType: string) {
    const nextPreset = providerPresets[providerType] || providerPresets.openai_compatible;
    setForm({
      ...form,
      provider_type: providerType,
      base_url: nextPreset.baseUrl,
      timeout_seconds: nextPreset.timeout,
      default_options: JSON.stringify(nextPreset.options, null, 2),
    });
    setMessage(`已载入 ${nextPreset.label} 默认配置，可继续修改。`);
  }

  function restoreDefaults() {
    setForm({
      ...form,
      base_url: preset.baseUrl,
      timeout_seconds: preset.timeout,
      default_options: JSON.stringify(preset.options, null, 2),
    });
    setMessage(`已恢复 ${preset.label} 推荐默认值，保存后生效。`);
  }

  function applyExperiment(options: Record<string, number>, name: string) {
    const current = parseJson<Record<string, unknown>>(form.default_options, {});
    const next = { ...current, ...options };
    if (form.provider_type === "ollama") {
      next.num_predict = next.max_tokens;
      delete next.max_tokens;
    }
    setForm({ ...form, default_options: JSON.stringify(next, null, 2) });
    setMessage(`已套用“${name}”，保存并测试后再用于正式章节。`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    let defaultOptions: Record<string, unknown>;
    try {
      defaultOptions = JSON.parse(form.default_options) as Record<string, unknown>;
    } catch {
      setMessage("默认参数不是有效 JSON，请检查逗号、引号和括号。");
      return;
    }
    const body = { ...form, default_options: defaultOptions };
    try {
      let providerId = selectedId;
      if (selectedId) {
        await api<ModelProvider>(`/model-providers/${selectedId}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
      } else {
        const created = await api<ModelProvider>("/model-providers", {
          method: "POST",
          body: JSON.stringify(body),
        });
        providerId = created.id;
      }
      setMessage("配置已保存；建议立即执行连接测试。");
      await load(providerId);
      await loadInventory();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "保存失败");
    }
  }

  async function remove() {
    if (!selectedId || !selectedProvider) return;
    if (!window.confirm(`删除模型配置“${selectedProvider.name}”？历史生成记录会保留，但不再关联此配置。`)) return;
    await api<void>(`/model-providers/${selectedId}`, { method: "DELETE" });
    const remaining = providers.filter((provider) => provider.id !== selectedId);
    setProviders(remaining);
    if (remaining.length > 0) {
      select(remaining[0]);
    } else {
      startNew();
    }
    setMessage("配置已删除。");
    await loadInventory();
  }

  async function test() {
    if (!selectedId) {
      setMessage("请先保存配置，再测试真实生成。");
      return;
    }
    setMessage("正在请求模型...");
    try {
      const result = await api<ProviderTestResult>(
        `/model-providers/${selectedId}/test`,
        { method: "POST" },
      );
      setDiagnostics(result);
      setMessage(`${result.ok ? "成功" : "失败"} · ${result.latency_ms} ms · ${result.response_preview || result.message}`);
      await load(selectedId);
      await loadInventory();
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "测试失败";
      setDiagnostics({ ok: false, message, latency_ms: 0, response_preview: "" });
      setMessage(message);
    }
  }

  function configureModel(model: LocalModelInfo) {
    const template = model.provider_template;
    if (!template) return;
    setSelectedId(null);
    setForm({
      name: String(template.name || model.name),
      provider_type: String(template.provider_type || "openai_compatible"),
      base_url: String(template.base_url || ""),
      model: String(template.model || model.name),
      api_key: "",
      default_options: JSON.stringify(template.default_options || {}, null, 2),
      timeout_seconds: Number(template.timeout_seconds || 300),
      enabled: Boolean(template.enabled ?? true),
    });
    setMessage(`已载入 ${model.name} 的默认配置；保存并测试后使用。`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <div className="space-y-6">
      <ModelRoleAssignments providers={providers} inventory={inventory} />

      <details className="panel overflow-hidden">
        <summary className="flex cursor-pointer list-none items-start justify-between gap-6 border-b border-black/10 bg-ink px-6 py-5 text-white">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-white/45">Model configuration</div>
            <h2 className="mt-1 font-serif text-3xl font-semibold">模型配置</h2>
            <p className="mt-2 text-sm text-white/55">展开管理全部 {providers.length} 个 Provider：选择或创建、改默认参数、真实请求验证。</p>
          </div>
          <span className="mt-1 shrink-0 rounded-full border border-white/15 px-3 py-1 text-xs text-white/60">{providers.length} 个 · 点击展开</span>
        </summary>

        <div className="flex items-center justify-end border-b border-black/10 bg-black/[0.02] px-5 py-3">
          <button className="rounded-xl border border-black/15 px-3 py-2 text-sm font-semibold hover:bg-white" onClick={() => startNew()}>
            + 新增配置
          </button>
        </div>

        <div className="grid grid-cols-[0.72fr_1.28fr]">
          <div className="border-r border-black/10 bg-black/[0.025] p-5">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="font-serif text-xl font-semibold">已有配置</h3>
              <span className="text-xs text-black/40">{providers.length} 个</span>
            </div>
            <div className="space-y-2">
              {providers.map((provider) => (
                <button
                  key={provider.id}
                  className={`w-full rounded-xl border p-3 text-left transition ${
                    selectedId === provider.id ? "border-moss bg-white shadow-sm" : "border-black/10 bg-white/50 hover:bg-white"
                  }`}
                  onClick={() => select(provider)}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="truncate font-semibold">{provider.name}</span>
                    <span className={`shrink-0 rounded-full px-2 py-1 text-[10px] font-bold ${
                      provider.last_test_status === "ok"
                        ? "bg-green-100 text-green-700"
                        : provider.last_test_status === "failed"
                          ? "bg-red-100 text-red-700"
                          : "bg-black/5 text-black/45"
                    }`}>
                      {statusLabel(provider.last_test_status)}
                    </span>
                  </div>
                  <div className="mt-1 truncate text-xs text-black/45">{provider.provider_type} · {provider.model || "未填写模型"}</div>
                  <code className="mt-2 block truncate rounded-lg bg-black/[0.035] px-2 py-1 text-[10px] text-black/45">
                    {provider.default_options_json}
                  </code>
                </button>
              ))}
              {providers.length === 0 && (
                <div className="rounded-xl border border-dashed border-black/15 p-5 text-center text-sm text-black/45">
                  尚无配置。点击“新增配置”或从下方本地模型载入默认值。
                </div>
              )}
            </div>
          </div>

          <form className="p-6" onSubmit={save}>
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <h3 className="font-serif text-2xl font-semibold">{selectedId ? "编辑模型配置" : "新建模型配置"}</h3>
                <p className="mt-1 text-xs leading-5 text-black/45">{preset.note}</p>
              </div>
              <span className="max-w-sm text-right text-sm text-moss">{message}</span>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div><label className="label">配置名称</label><input className="field" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></div>
              <div>
                <label className="label">运行时类型</label>
                <select className="field" value={form.provider_type} onChange={(e) => changeProviderType(e.target.value)}>
                  {Object.entries(providerPresets).map(([value, item]) => <option key={value} value={value}>{item.label}</option>)}
                </select>
              </div>
              <div className="col-span-2">
                <label className="label">Base URL</label>
                <input className="field font-mono text-xs" value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} required />
                <p className="mt-1 text-[11px] text-black/40">修改场景：服务端口变化、使用另一台局域网设备，或接口带有 /v1 前缀。</p>
              </div>
              <div>
                <label className="label">模型名称 / Alias</label>
                <input className="field" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} required />
                <p className="mt-1 text-[11px] text-black/40">必须与服务暴露的模型 ID 一致。</p>
              </div>
              <div>
                <label className="label">请求超时（秒）</label>
                <input className="field" type="number" min={5} max={3600} value={form.timeout_seconds} onChange={(e) => setForm({ ...form, timeout_seconds: Number(e.target.value) })} />
                <p className="mt-1 text-[11px] text-black/40">大模型首次加载可设为 600-1200 秒。</p>
              </div>
              <div className="col-span-2">
                <label className="label">API Key（本地服务通常留空）</label>
                <input className="field" type="password" value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} autoComplete="off" />
              </div>
              <div className="col-span-2">
                <div className="mb-1 flex items-center justify-between">
                  <label className="label mb-0">默认生成参数 JSON</label>
                  <button type="button" className="text-xs font-semibold text-moss hover:underline" onClick={restoreDefaults}>恢复此类型默认值</button>
                </div>
                <textarea className="field min-h-48 font-mono text-xs leading-5" value={form.default_options} onChange={(e) => setForm({ ...form, default_options: e.target.value })} spellCheck={false} />
                <p className="mt-1 text-[11px] text-black/40">可直接编辑字段或使用下方实验方案。章节任务临时参数会覆盖这里的同名字段。</p>
              </div>
            </div>

            <label className="mt-4 flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
              启用此配置并允许写作工作区选择
            </label>
            <div className="mt-5 flex items-center justify-end gap-3 border-t border-black/10 pt-5">
              <div className="flex gap-3">
                <button type="button" className="btn-soft" disabled={!selectedId} onClick={() => void test()}>测试真实生成</button>
                <button className="btn-primary">{selectedId ? "保存修改" : "保存新配置"}</button>
              </div>
            </div>
            <ProviderDiagnosticsCard provider={selectedProvider} result={diagnostics} />
          </form>
        </div>
      </details>

      <details className="panel p-6">
        <summary className="cursor-pointer list-none">
          <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-rust">Tune and compare</div>
          <h2 className="mt-1 font-serif text-2xl font-semibold">高级参数与实验方案</h2>
          <p className="mt-2 text-sm text-black/50">每次只改变一到两个参数，用同一章节大纲生成备选版本，再比较一致性、文风、重复率和耗时。</p>
        </summary>

        <div className="mt-5 grid grid-cols-2 gap-6">
          <div>
            <h3 className="mb-3 font-semibold">可修改参数</h3>
            <div className="overflow-hidden rounded-xl border border-black/10">
              {parameterGuide.map(([key, label, range, description]) => (
                <div key={key} className="grid grid-cols-[1fr_0.8fr_2fr] gap-3 border-b border-black/5 bg-white/50 px-4 py-3 text-xs last:border-0">
                  <div><code className="font-semibold text-rust">{key}</code><div className="mt-1 text-black/40">{label}</div></div>
                  <div className="font-mono text-black/55">{range}</div>
                  <div className="leading-5 text-black/55">{description}</div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <h3 className="mb-3 font-semibold">一键套用实验方案</h3>
            <div className="grid grid-cols-2 gap-3">
              {experiments.map((experiment) => (
                <article key={experiment.name} className="rounded-xl border border-black/10 bg-white/55 p-4">
                  <div className="font-semibold">{experiment.name}</div>
                  <p className="mt-1 min-h-10 text-xs leading-5 text-black/50">{experiment.description}</p>
                  <code className="mt-3 block rounded-lg bg-ink p-2 text-[10px] leading-4 text-white/65">
                    {JSON.stringify(experiment.options)}
                  </code>
                  <button className="btn-soft mt-3 w-full" onClick={() => applyExperiment(experiment.options, experiment.name)}>套用到当前表单</button>
                </article>
              ))}
            </div>
            <div className="mt-3 rounded-xl bg-amber-50 p-4 text-xs leading-5 text-amber-900">
              建议流程：保存配置 → 测试真实生成 → 用同一大纲生成 2-3 个版本 → 保留最佳参数。创意参数仅用于备选稿，确认后再写入正式正文。
            </div>
          </div>
        </div>
      </details>

      <details>
        <summary className="panel flex cursor-pointer list-none items-center justify-between px-6 py-4">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-rust">Local inventory</div>
            <h2 className="mt-0.5 font-serif text-xl font-semibold">本地模型清单（扫描已安装模型）</h2>
          </div>
          <span className="rounded-full border border-black/10 px-3 py-1 text-xs text-black/45">点击展开</span>
        </summary>
        <div className="mt-3">
          <LocalModelCenter
            inventory={inventory}
            loading={inventoryLoading}
            error={inventoryError}
            onRefresh={() => void loadInventory()}
            onConfigure={configureModel}
          />
        </div>
      </details>

      <CheckerBenchPanel />
      <WriterBenchPanel />
    </div>
  );
}
