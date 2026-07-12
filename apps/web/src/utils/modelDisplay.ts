import type { LocalModelInfo, LocalModelInventory, ModelProvider } from "../types";

export function localModelForProvider(
  provider: ModelProvider,
  inventory: LocalModelInventory | null,
): LocalModelInfo | null {
  return inventory?.models.find((model) =>
    model.name === provider.model
    || String(model.provider_template?.model || "") === provider.model
  ) || null;
}

export type ModelService = "omlx" | "lmstudio" | "ollama" | "llamacpp" | "other";

// 服务判定按 base_url 端口（最可靠）：provider_type 不可靠——真实数据里能用的 oMLX/LM Studio
// 很多是 openai_compatible 类型，靠端口才能正确归到服务。1234=LM Studio，8003/8000=oMLX。
export function serviceOf(provider: ModelProvider): ModelService {
  const url = String(provider.base_url || "");
  if (url.includes(":1234")) return "lmstudio";
  if (url.includes(":8003") || url.includes(":8000")) return "omlx";
  if (url.includes(":11434")) return "ollama";
  if (url.includes(":18081")) return "llamacpp";
  return "other";
}

export const serviceLabels: Record<ModelService, string> = {
  omlx: "oMLX",
  lmstudio: "LM Studio",
  ollama: "Ollama",
  llamacpp: "本机 llama.cpp",
  other: "其它",
};

const UNCENSORED_RE = /uncensor|abliterat|heretic|crack|jang|deckard|hauhaucs|aggressive|josiefied|去审核/i;
// 改版 = 社区蒸馏/合并（非官方基座，也未必去审核）：Claude/Opus 蒸馏、qwopus 合并、preview/imatrix 等。
const REMIX_RE = /opus|claude|distil|reasoning|qwopus|preview|imatrix|[-_]neo[-_]?|[-_]mtp\b|merge|fusion/i;

export function isUncensored(provider: ModelProvider): boolean {
  return UNCENSORED_RE.test(provider.name || "") || UNCENSORED_RE.test(provider.model || "");
}

// 「改版」具体优化点：从模型名推断社区改的是什么，简短标注（答"改版优化的点是什么"）。
// 仅用于非去审核的改版模型；去审核走"去审核"标，官方走"官方版"。
export function remixNote(provider: ModelProvider): string {
  const hay = `${provider.name || ""} ${provider.model || ""}`.toLowerCase();
  const hasOpusOrClaude = /opus|claude/.test(hay);
  const hasReasoning = /reasoning|thinking/.test(hay);
  const hasDistil = /distil/.test(hay);
  if (/qwopus/.test(hay)) return "qwopus合并";
  if (hasOpusOrClaude && hasReasoning && hasDistil) return "Opus推理蒸馏";
  if (hasOpusOrClaude && hasReasoning) return "Opus推理";
  if (hasOpusOrClaude && hasDistil) return "Opus蒸馏";
  if (hasOpusOrClaude) return "Opus版";
  if (hasReasoning) return "推理版";
  if (/merge|fusion/.test(hay)) return "合并版";
  if (/preview/.test(hay)) return "预览版";
  return "改版";
}

// 版本标签：去审核 > 改版(蒸馏/合并) > 官方版(真·官方基座 instruct)。非去审核也总给个标，避免空白。
export function versionTag(provider: ModelProvider): string {
  if (isUncensored(provider)) return "去审核";
  const hay = `${provider.name || ""} ${provider.model || ""}`;
  if (REMIX_RE.test(hay)) return "改版";
  return "官方版";
}

// 友好命名用的类别徽章：去审核 / 具体改版点(Opus蒸馏…) / 官方版。
function categoryBadge(provider: ModelProvider): string {
  if (isUncensored(provider)) return "去审核";
  const hay = `${provider.name || ""} ${provider.model || ""}`;
  if (REMIX_RE.test(hay)) return remixNote(provider);
  return "官方版";
}

const FAMILIES = ["qwen", "gemma", "llama", "mistral", "deepseek", "yi", "phi", "gpt"];

// 从又长又乱的模型名里抽出"家族+参数量"短名：
// "qwen3.6-40b-claude-...-imatrix-max" → "Qwen3.6 40B"；"Josiefied-Qwen3-14B-abliterated" → "Qwen3 14B"。
function shortModelName(raw: string, fallbackParam: string): string {
  const lower = raw.toLowerCase();
  let family = "";
  for (const f of FAMILIES) {
    const idx = lower.indexOf(f);
    if (idx >= 0) {
      const m = raw.slice(idx).match(/^([A-Za-z]+[\d.]*)/);
      family = m ? m[1] : f;
      break;
    }
  }
  const pm = raw.match(/(\d+\.?\d*b(?:[-_]a\d+\.?\d*b)?)/i);
  const param = pm ? pm[1].toUpperCase() : fallbackParam;
  const cap = family ? family.charAt(0).toUpperCase() + family.slice(1) : "";
  return [cap, param].filter(Boolean).join(" ").trim() || raw.replace(/[-_]/g, " ").slice(0, 22);
}

function stripServicePrefix(name: string): string {
  return name.replace(/^\s*(LM Studio|oMLX|Ollama|本机 llama\.cpp|Local llama\.cpp|去审核)\s*·?\s*/i, "").trim();
}

// 友好命名：「[去审核 ·] 体积G · 模型简名 [· ✓已验证]」，简单易看懂。
export function friendlyModelLabel(
  provider: ModelProvider,
  inventory: LocalModelInventory | null,
): string {
  const model = localModelForProvider(provider, inventory);
  const raw = stripServicePrefix(provider.name) || provider.model;
  const param = model ? String(model.details.parameters || model.details.parameter_size || "") : "";
  const short = shortModelName(raw, param);
  const sizeG = model?.size_label ? String(model.size_label).replace(/\s*GB/i, "G") : "";
  return [
    categoryBadge(provider),
    sizeG,
    short,
    provider.last_test_status === "ok" ? "✓已验证" : "",
  ].filter(Boolean).join(" · ");
}

// 从名字/清单里抽参数量（十亿）。MoE 的 "35B-A3B" 取总参 35。
export function paramOf(provider: ModelProvider, inventory: LocalModelInventory | null): number {
  const raw = `${provider.name || ""} ${provider.model || ""}`;
  const m = raw.match(/(\d+\.?\d*)\s*b\b/i) || raw.match(/(\d+\.?\d*)b/i);
  if (m) return parseFloat(m[1]);
  const model = localModelForProvider(provider, inventory);
  const p = model ? String(model.details.parameters || model.details.parameter_size || "") : "";
  const pm = p.match(/(\d+\.?\d*)/);
  return pm ? parseFloat(pm[1]) : 0;
}

export type RoleKind = "deconstruct" | "writer" | "checker" | "summary";

// 角色推荐（基于 2026 社区/榜单结论）：
// - deconstruct 拆解：oMLX + 去审核 + 小(~14B 甜点)，并发快、JSON 稳、露骨不拒答。
// - writer 正文：大而强(~35B 甜点)，优先已验证、偏写作向。
// - checker 检查：推理/蒸馏模型(~27B 甜点)，排除去审核(实测召回0)，思考由后端强制开。
// - summary 摘要：小而快即可，优先已验证。
// 返回 provider id（找不到返回 ""）。inventory 可为 null（参数量退回名字解析）。
export function recommendProvider(
  providers: ModelProvider[],
  inventory: LocalModelInventory | null,
  role: RoleKind,
): string {
  const enabled = providers.filter((p) => p.enabled);
  if (enabled.length === 0) return "";
  const ok = (p: ModelProvider) => (p.last_test_status === "ok" ? 1 : 0);
  const param = (p: ModelProvider) => paramOf(p, inventory);
  // 只在用户实际使用的服务（LM Studio / oMLX）里推荐，避免落到 Ollama / 本机 llama.cpp 的小模型上。
  const visible = enabled.filter((p) => serviceOf(p) === "lmstudio" || serviceOf(p) === "omlx");
  const base = visible.length ? visible : enabled;

  if (role === "deconstruct") {
    const omlx = base.filter((p) => serviceOf(p) === "omlx");
    const pool = omlx.length ? omlx : base;
    const ranked = [...pool].sort(
      (a, b) =>
        (Number(isUncensored(b)) - Number(isUncensored(a))) ||
        (ok(b) - ok(a)) ||
        (Math.abs(param(a) - 14) - Math.abs(param(b) - 14)),
    );
    return ranked[0]?.id || "";
  }
  if (role === "writer") {
    const big = base.filter((p) => param(p) >= 24);
    const pool = big.length ? big : base;
    const ranked = [...pool].sort(
      (a, b) => (ok(b) - ok(a)) || (Math.abs(param(a) - 35) - Math.abs(param(b) - 35)),
    );
    return ranked[0]?.id || "";
  }
  if (role === "checker") {
    // 检查：实测结论——去审核(abliterated)模型推理被阉割、召回0，绝不能用；
    // 需要"会思考"的推理/蒸馏模型，~27B 甜点（Opus 蒸馏实测 100% 召回）。思考由后端强制开启。
    const isRemix = (p: ModelProvider) => REMIX_RE.test(`${p.name || ""} ${p.model || ""}`);
    const sober = base.filter((p) => !isUncensored(p)); // 排除去审核
    const pool = sober.length ? sober : base;
    const ranked = [...pool].sort(
      (a, b) =>
        (Number(isRemix(b)) - Number(isRemix(a))) ||      // 推理/蒸馏优先
        (ok(b) - ok(a)) ||                                  // 已验证优先
        (Math.abs(param(a) - 27) - Math.abs(param(b) - 27)),// ~27B 甜点
    );
    return ranked[0]?.id || "";
  }
  // summary 摘要：轻任务，小而快即可（<7B 跑不动 JSON），目标 ~8B；优先 7–16B、已验证、最接近 9。
  const capable = base.filter((p) => param(p) >= 7);
  const pool = capable.length ? capable : base;
  const inRange = (p: ModelProvider) => (param(p) >= 7 && param(p) <= 16 ? 0 : 1);
  const ranked = [...pool].sort(
    (a, b) => (inRange(a) - inRange(b)) || (ok(b) - ok(a)) || (Math.abs(param(a) - 9) - Math.abs(param(b) - 9)),
  );
  return ranked[0]?.id || "";
}

export function providerOptionLabel(
  provider: ModelProvider,
  inventory: LocalModelInventory | null,
): string {
  const model = localModelForProvider(provider, inventory);
  if (!model) return `${provider.name} · ${provider.model}`;
  const parameters = String(model.details.parameters || model.details.parameter_size || "").trim();
  const quantization = String(model.details.quantization || "").trim();
  const memory = String(model.details.runtime_memory_gb_estimate || "").trim();
  return [
    provider.name,
    parameters,
    quantization,
    `本体 ${model.size_label}`,
    memory ? `运行约 ${memory}` : "",
    provider.last_test_status === "ok" ? "已验证" : "本地已安装",
  ].filter(Boolean).join(" · ");
}
