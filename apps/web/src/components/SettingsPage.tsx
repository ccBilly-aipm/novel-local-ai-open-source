import { useState } from "react";
import ModelSettings from "./ModelSettings";
import PromptManager from "./PromptManager";

export type SettingsTab = "models" | "prompts" | "app";

const tabs: [SettingsTab, string, string][] = [
  ["models", "本地模型", "Provider、任务分配、推荐与参数"],
  ["prompts", "提示词", "全部提示词，可编辑即时生效"],
  ["app", "应用", "本地数据与存储"],
];

export default function SettingsPage({ initialTab = "models" }: { initialTab?: SettingsTab }) {
  const [tab, setTab] = useState<SettingsTab>(initialTab);
  return (
    <main className="mx-auto max-w-7xl p-7">
      <div className="mb-5">
        <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-rust">Settings</div>
        <h1 className="mt-1 font-serif text-3xl font-semibold">设置</h1>
      </div>

      <div className="mb-6 flex gap-1 border-b border-black/10">
        {tabs.map(([key, label, desc]) => (
          <button
            key={key}
            className={`relative px-5 py-3 text-left ${tab === key ? "text-ink" : "text-black/45 hover:text-black/70"}`}
            onClick={() => setTab(key)}
          >
            <span className="text-sm font-semibold">{label}</span>
            <span className="ml-2 hidden text-[11px] text-black/35 lg:inline">{desc}</span>
            {tab === key && <span className="absolute inset-x-3 bottom-0 h-0.5 bg-rust" />}
          </button>
        ))}
      </div>

      {tab === "models" && <ModelSettings />}
      {tab === "prompts" && <PromptManager />}
      {tab === "app" && (
        <section className="panel p-8">
          <h2 className="font-serif text-2xl font-semibold">本地数据</h2>
          <p className="mt-3 text-sm leading-6 text-black/55">
            全部数据保存在本机 SQLite（项目、章节、版本、运行记录、模型 Provider、提示词均在本地）。
            模型与提示词的管理已并入本页上方的「本地模型」「提示词」标签。
          </p>
          <div className="mt-4 inline-flex items-center gap-2 rounded-full bg-black/[0.04] px-3 py-1.5 text-xs text-black/55">
            本地数据 · SQLite
          </div>
        </section>
      )}
    </main>
  );
}
