import { useEffect, useMemo, useState } from "react";
import type { LocalModelInventory, ModelProvider } from "../../types";
import { friendlyModelLabel, recommendProvider } from "../../utils/modelDisplay";

interface Props {
  providers: ModelProvider[];
  inventory: LocalModelInventory | null;
}

const roleKeys = {
  writer: "novel-local-ai.writer-provider-id",
  checker: "novel-local-ai.checker-provider-id",
  summary: "novel-local-ai.summary-provider-id",
} as const;

type Role = keyof typeof roleKeys;
const ROLES: Role[] = ["writer", "checker", "summary"];

const roleMeta: Record<Role, { label: string; desc: string; reason: string }> = {
  writer: {
    label: "正文模型",
    desc: "章节工作区启动 Loop 的默认正文模型。",
    reason: "推荐大模型 ≈35B：64GB Mac 最佳档，文笔与结构承载最好",
  },
  checker: {
    label: "检查模型",
    desc: "自动模式下的连续性检查 / 状态抽取。",
    reason: "推荐推理模型 ≈27B（如 Opus 蒸馏）：实测唯一能稳定抓出跨章矛盾；去审核模型会漏检，勿用",
  },
  summary: {
    label: "摘要模型",
    desc: "章节摘要（低成本任务）。",
    reason: "推荐小快模型：摘要不需要大模型",
  },
};

export default function ModelRoleAssignments({ providers, inventory }: Props) {
  const enabled = useMemo(() => providers.filter((p) => p.enabled), [providers]);
  const recs = useMemo(
    () => ({
      writer: recommendProvider(providers, inventory, "writer"),
      checker: recommendProvider(providers, inventory, "checker"),
      summary: recommendProvider(providers, inventory, "summary"),
    }),
    [providers, inventory],
  );
  const deconRec = useMemo(() => recommendProvider(providers, inventory, "deconstruct"), [providers, inventory]);
  const [values, setValues] = useState<Record<Role, string>>({ writer: "", checker: "", summary: "" });

  useEffect(() => {
    const next = {} as Record<Role, string>;
    ROLES.forEach((role) => {
      const stored = window.localStorage.getItem(roleKeys[role]);
      next[role] = stored || recs[role];
      if (!stored && next[role]) window.localStorage.setItem(roleKeys[role], next[role]);
    });
    setValues(next);
  }, [recs]);

  function set(role: Role, id: string) {
    window.localStorage.setItem(roleKeys[role], id);
    setValues((v) => ({ ...v, [role]: id }));
  }
  function applyAll() {
    ROLES.forEach((role) => {
      if (recs[role]) set(role, recs[role]);
    });
  }

  const labelOf = (id: string) => {
    const p = enabled.find((x) => x.id === id);
    return p ? friendlyModelLabel(p, inventory) : "未指定";
  };
  const allApplied = ROLES.every((role) => values[role] === recs[role]);

  return (
    <section className="panel p-6">
      <div className="flex items-start justify-between gap-6">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-rust">推荐配置 · Task roles</div>
          <h2 className="mt-1 font-serif text-3xl font-semibold">推荐与任务分配</h2>
          <p className="mt-2 text-sm text-black/50">
            按"哪个模型做什么"分工——大模型写正文、小快模型做检查。选择保存在本浏览器，可随时改。
          </p>
        </div>
        <button
          className={`shrink-0 rounded-xl px-4 py-2.5 text-sm font-semibold ${
            allApplied ? "cursor-default bg-black/5 text-black/35" : "bg-rust text-white hover:opacity-90"
          }`}
          disabled={allApplied}
          onClick={applyAll}
        >
          {allApplied ? "✓ 已按推荐" : "一键采用全部推荐"}
        </button>
      </div>

      <div className="mt-5 grid grid-cols-3 gap-4">
        {ROLES.map((role) => {
          const meta = roleMeta[role];
          const current = values[role];
          const recId = recs[role];
          const isRec = current === recId && !!recId;
          const selected = enabled.find((p) => p.id === current);
          return (
            <div key={role} className="flex flex-col rounded-2xl border border-black/10 bg-white/55 p-4">
              <div className="flex items-center justify-between">
                <div className="font-semibold">{meta.label}</div>
                {isRec && (
                  <span className="rounded-full bg-moss/10 px-2 py-0.5 text-[10px] font-bold text-moss">★ 按推荐</span>
                )}
              </div>
              <p className="mt-1 min-h-8 text-xs leading-5 text-black/45">{meta.desc}</p>

              {/* 推荐项 + 理由 */}
              <div className="mt-2 rounded-xl bg-amber-50/70 px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[11px] font-semibold text-amber-900">推荐：{labelOf(recId)}</span>
                  {!isRec && recId && (
                    <button
                      className="shrink-0 rounded-md bg-amber-200/70 px-2 py-0.5 text-[10px] font-bold text-amber-900 hover:bg-amber-200"
                      onClick={() => set(role, recId)}
                    >
                      用推荐
                    </button>
                  )}
                </div>
                <p className="mt-1 text-[10px] leading-4 text-amber-800/80">{meta.reason}</p>
              </div>

              {/* 当前选择（mt-auto 让选框在等高卡片里底部对齐） */}
              <div className="mt-auto pt-3">
                <select className="field" value={current} onChange={(e) => set(role, e.target.value)}>
                  <option value="">未指定</option>
                  {enabled.map((p) => (
                    <option key={p.id} value={p.id}>{friendlyModelLabel(p, inventory)}</option>
                  ))}
                </select>
                <div className="mt-2 text-[10px]">
                  <span className={selected?.last_test_status === "ok" ? "text-green-700" : selected?.last_test_status === "failed" ? "text-red-700" : "text-black/40"}>
                    {selected?.last_test_status === "ok" ? "连通性已验证" : selected?.last_test_status === "failed" ? "最近测试失败" : "尚未测试"}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 rounded-xl bg-black/[0.035] px-4 py-3 text-xs leading-5 text-black/55">
        <b>拆解 / 分析小说</b>：推荐 <b>oMLX 去审核 ≈14B</b>（{labelOf(deconRec) || "未配置 oMLX 模型"}）——
        露骨内容不拒答、并发快、JSON 稳。该默认在「创作中心」进入拆解模式时自动选中，无需在此设置。
      </div>
      <p className="mt-2 px-1 text-[10px] leading-4 text-black/40">
        「✓已验证」= 连通性测试通过（能连上、能出话），<b>不代表生成质量</b>；名称里的「Opus蒸馏 / qwopus合并」是该改版的优化方向。
        各模型在「检查」任务上的<b>真实效果</b>见本页最下方「模型测试 · 连续性检查」。
      </p>
      {enabled.length === 0 && (
        <div className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">先在下方"模型配置"创建并启用至少一个 Provider。</div>
      )}
    </section>
  );
}
