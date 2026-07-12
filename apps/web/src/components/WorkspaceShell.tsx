import { useState } from "react";
import type { Novel, Project } from "../types";
import CharacterCards from "./CharacterCards";
import CreativeStudio from "./CreativeStudio";
import PromptManager from "./PromptManager";
import Workspace from "./Workspace";
import Worldbuilding from "./Worldbuilding";

interface Props {
  project: Project;
  novel: Novel;
  onNovelChange: (novel: Novel) => void;
  onBack: () => void;
}

const tabs = [
  ["create", "创作中心"],
  ["workspace", "章节编辑"],
  ["characters", "角色卡"],
  ["world", "世界观"],
  ["prompts", "Prompt 模板"],
] as const;

export default function WorkspaceShell({ project, novel, onNovelChange, onBack }: Props) {
  const [tab, setTab] = useState<(typeof tabs)[number][0]>("create");

  return (
    <div className="min-h-screen">
      <header className="flex h-16 items-center border-b border-black/10 bg-ink px-5 text-white">
        <button className="mr-5 text-sm text-white/60 hover:text-white" onClick={onBack}>
          ← 项目
        </button>
        <div className="mr-auto">
          <div className="text-[10px] uppercase tracking-[0.2em] text-white/45">{project.name}</div>
          <div className="font-serif text-lg font-semibold">{novel.title}</div>
        </div>
        <nav className="flex gap-1">
          {tabs.map(([key, label]) => (
            <button
              key={key}
              className={`rounded-lg px-3 py-2 text-sm ${
                tab === key ? "bg-white text-ink" : "text-white/60 hover:bg-white/10 hover:text-white"
              }`}
              onClick={() => setTab(key)}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>

      {tab === "create" && <CreativeStudio novel={novel} onNovelChange={onNovelChange} onOpenChapters={() => setTab("workspace")} />}
      {tab === "workspace" && <Workspace novel={novel} onNovelChange={onNovelChange} />}
      {tab === "characters" && <CharacterCards novelId={novel.id} />}
      {tab === "world" && <Worldbuilding novelId={novel.id} />}
      {tab === "prompts" && <PromptManager />}
    </div>
  );
}
