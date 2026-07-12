import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { PromptTemplate } from "../types";

// 按 key 前缀归组（与后端注册表一致），让 ~28 个提示词分门别类、好找。
const GROUPS: { title: string; match: (key: string) => boolean }[] = [
  { title: "拆解（逆向）", match: (k) => k.startsWith("decon_") },
  { title: "故事工程 / 仿写", match: (k) => k.startsWith("se_") },
  { title: "Loop 循环", match: (k) => k.startsWith("loop_") },
  { title: "旧版生产", match: (k) => !k.startsWith("decon_") && !k.startsWith("se_") && !k.startsWith("loop_") },
];

export default function PromptManager() {
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [selected, setSelected] = useState<PromptTemplate | null>(null);
  const [text, setText] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    const data = await api<PromptTemplate[]>("/prompt-templates");
    setTemplates(data);
    if (selected) {
      const fresh = data.find((item) => item.id === selected.id) || null;
      setSelected(fresh);
      setText(fresh?.template_text || "");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="grid grid-cols-[0.65fr_1.35fr] gap-6">
      <section className="panel p-5">
        <h2 className="mb-1 font-serif text-2xl font-semibold">Prompt 模板</h2>
        <p className="mb-4 text-xs text-black/40">全部提示词均可在此编辑，保存后即时生效（DB 覆盖打包文件）。</p>
        <div className="space-y-5">
          {GROUPS.map((group) => {
            const items = templates.filter((t) => group.match(t.key));
            if (items.length === 0) return null;
            return (
              <div key={group.title}>
                <div className="mb-2 text-[10px] font-bold uppercase tracking-[0.18em] text-black/35">
                  {group.title} · {items.length}
                </div>
                <div className="space-y-2">
                  {items.map((template) => (
                    <button
                      key={template.id}
                      className={`w-full rounded-xl border p-3 text-left ${selected?.id === template.id ? "border-moss bg-moss/5" : "border-black/10 bg-white/50"}`}
                      onClick={() => { setSelected(template); setText(template.template_text); setMessage(""); }}
                    >
                      <div className="font-mono text-xs font-bold text-rust">{template.key}</div>
                      <div className="mt-1 font-semibold">{template.name}</div>
                      <div className="text-xs text-black/40">v{template.version}</div>
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </section>
      <section className="panel p-6">
        {selected ? (
          <>
            <div className="mb-4 flex items-start justify-between">
              <div><h2 className="font-serif text-2xl font-semibold">{selected.name}</h2><p className="mt-1 text-sm text-black/50">{selected.description}</p></div>
              <span className="text-sm text-moss">{message}</span>
            </div>
            <textarea className="field min-h-[560px] font-mono text-xs leading-6" value={text} onChange={(e) => setText(e.target.value)} />
            <div className="mt-4 flex items-center justify-between">
              <code className="text-xs text-black/45">占位符使用 {"{{variable}}"}</code>
              <button
                className="btn-primary"
                onClick={async () => {
                  await api<PromptTemplate>(`/prompt-templates/${selected.id}`, {
                    method: "PATCH",
                    body: JSON.stringify({ template_text: text }),
                  });
                  setMessage("已保存新版本");
                  await load();
                }}
              >
                保存模板
              </button>
            </div>
          </>
        ) : (
          <div className="grid min-h-[620px] place-items-center text-black/40">选择一个模板查看和编辑</div>
        )}
      </section>
    </div>
  );
}
