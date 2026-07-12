import { FormEvent, useEffect, useState } from "react";
import { api } from "../services/api";
import type { WorldRule } from "../types";

interface Props {
  novelId: string;
}

export default function Worldbuilding({ novelId }: Props) {
  const [rules, setRules] = useState<WorldRule[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", category: "general", description: "", priority: 50 });

  async function load() {
    setRules(await api<WorldRule[]>(`/novels/${novelId}/world-rules`));
  }

  useEffect(() => {
    void load();
  }, [novelId]);

  async function save(event: FormEvent) {
    event.preventDefault();
    const body = { ...form, novel_id: novelId };
    if (selectedId) {
      await api<WorldRule>(`/world-rules/${selectedId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
    } else {
      await api<WorldRule>("/world-rules", { method: "POST", body: JSON.stringify(body) });
    }
    setSelectedId(null);
    setForm({ name: "", category: "general", description: "", priority: 50 });
    await load();
  }

  return (
    <main className="mx-auto grid max-w-7xl grid-cols-[0.8fr_1.2fr] gap-6 p-7">
      <section className="panel p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-serif text-2xl font-semibold">世界观条目</h2>
          <button className="btn-soft" onClick={() => { setSelectedId(null); setForm({ name: "", category: "general", description: "", priority: 50 }); }}>+ 新规则</button>
        </div>
        <div className="space-y-2">
          {rules.map((rule) => (
            <button
              key={rule.id}
              className={`w-full rounded-xl border p-3 text-left ${selectedId === rule.id ? "border-moss bg-moss/5" : "border-black/10 bg-white/50"}`}
              onClick={() => {
                setSelectedId(rule.id);
                setForm({ name: rule.name, category: rule.category, description: rule.description, priority: rule.priority });
              }}
            >
              <div className="flex justify-between"><span className="font-semibold">{rule.name}</span><span className="text-xs text-black/40">P{rule.priority}</span></div>
              <div className="text-xs text-black/45">{rule.category}</div>
            </button>
          ))}
        </div>
      </section>
      <form className="panel p-6" onSubmit={save}>
        <h2 className="mb-5 font-serif text-2xl font-semibold">{selectedId ? "编辑规则" : "新建规则"}</h2>
        <label className="label">名称</label>
        <input className="field mb-4" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <div className="mb-4 grid grid-cols-2 gap-4">
          <div>
            <label className="label">分类</label>
            <select className="field" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              <option value="general">通用规则</option>
              <option value="location">地点</option>
              <option value="organization">组织</option>
              <option value="item">物品</option>
              <option value="magic">能力 / 魔法</option>
              <option value="history">历史</option>
            </select>
          </div>
          <div><label className="label">上下文优先级 0-100</label><input className="field" type="number" min={0} max={100} value={form.priority} onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })} /></div>
        </div>
        <label className="label">条目描述</label>
        <textarea className="field min-h-64" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        <div className="mt-5 flex justify-between">
          <button
            type="button"
            className="btn-soft text-red-700"
            disabled={!selectedId}
            onClick={async () => {
              if (!selectedId || !window.confirm("删除这条世界规则？")) return;
              await api<void>(`/world-rules/${selectedId}`, { method: "DELETE" });
              setSelectedId(null);
              setForm({ name: "", category: "general", description: "", priority: 50 });
              await load();
            }}
          >
            删除
          </button>
          <button className="btn-primary">保存世界观条目</button>
        </div>
      </form>
    </main>
  );
}
