import { ChangeEvent, useState } from "react";
import { api } from "../services/api";
import type { ChapterLoopRunSummary, ModelProvider, Project } from "../types";
import CreateProjectDialog from "../features/projects/CreateProjectDialog";
import ProjectCardV2 from "../features/projects/ProjectCardV2";

interface Props {
  projects: Project[];
  runs: ChapterLoopRunSummary[];
  providers: ModelProvider[];
  error: string;
  onRefresh: () => Promise<void>;
  onOpen: (projectId: string) => void;
  onOpenRun: (run: ChapterLoopRunSummary) => void;
  onOpenModels: () => void;
  onAnalyze: (text: string, name: string) => Promise<void>;
}

export default function Dashboard({
  projects,
  runs,
  providers,
  error,
  onRefresh,
  onOpen,
  onOpenRun,
  onOpenModels,
  onAnalyze,
}: Props) {
  const [creating, setCreating] = useState(false);

  async function onPickNovel(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      window.alert("文件过大，单个素材限 2MB，请先拆分长文。");
      return;
    }
    const text = await file.text();
    const cleaned = file.name.replace(/\.(txt|md)$/i, "") || "未命名分析";
    await onAnalyze(text, cleaned);
    event.target.value = "";
  }
  const waiting = runs.filter((run) => run.status === "waiting").length;
  const active = runs.filter((run) => run.status === "running" || run.status === "pending").length;
  const failed = runs.filter((run) => run.status === "failed").length;
  const healthyProviders = providers.filter((provider) => provider.enabled && provider.last_test_status === "ok").length;

  async function removeProject(projectId: string) {
    if (!window.confirm("删除项目及其全部本地数据？此操作不可撤销。")) return;
    await api<void>(`/projects/${projectId}`, { method: "DELETE" });
    await onRefresh();
  }

  return (
    <main className="mx-auto max-w-7xl px-8 py-9">
      <header className="mb-8 flex items-end justify-between gap-8">
        <div>
          <div className="mb-2 text-xs font-bold uppercase tracking-[0.28em] text-rust">Projects</div>
          <h1 className="font-serif text-4xl font-semibold tracking-tight">分析、解构、仿写小说</h1>
          <p className="mt-2 max-w-2xl text-sm text-black/50">用本地模型拆解一篇参考小说，或从一个想法开始。上传小说即自动建项目并进入拆解。</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="btn-primary cursor-pointer px-5">
            分析一篇小说
            <input className="hidden" type="file" accept=".txt,.md,text/plain,text/markdown" onChange={(event) => void onPickNovel(event)} />
          </label>
          <button className="btn-soft px-5" onClick={() => setCreating(true)}>+ 新建项目</button>
        </div>
      </header>

      {error && <div className="mb-6 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

      <section className="mb-7 grid grid-cols-4 gap-3">
        <div className="panel p-4"><div className="text-xs text-black/45">待人工审批</div><div className="mt-1 text-2xl font-bold text-amber-800">{waiting}</div></div>
        <div className="panel p-4"><div className="text-xs text-black/45">正在运行</div><div className="mt-1 text-2xl font-bold text-blue-700">{active}</div></div>
        <div className="panel p-4"><div className="text-xs text-black/45">需要处理的失败</div><div className="mt-1 text-2xl font-bold text-red-700">{failed}</div></div>
        <button className="panel p-4 text-left hover:border-moss" onClick={onOpenModels}>
          <div className="text-xs text-black/45">可用模型连接</div>
          <div className="mt-1 text-2xl font-bold text-moss">{healthyProviders}</div>
        </button>
      </section>

      {projects.length ? (
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-bold">本地项目</h2>
            <span className="text-sm text-black/40">{projects.length} 个项目</span>
          </div>
          <div className="grid grid-cols-3 gap-4">
            {projects.map((project) => (
              <ProjectCardV2
                key={project.id}
                project={project}
                runs={runs}
                onOpen={onOpen}
                onOpenRun={onOpenRun}
                onDelete={removeProject}
              />
            ))}
          </div>
        </section>
      ) : (
        <section className="panel grid min-h-80 place-items-center p-10 text-center">
          <div>
            <div className="mx-auto mb-5 grid h-14 w-14 place-items-center rounded-2xl bg-moss/10 font-serif text-2xl text-moss">N</div>
            <h2 className="font-serif text-2xl font-semibold">还没有小说项目</h2>
            <p className="mt-2 text-sm text-black/45">最快上手：直接上传一篇小说让本地模型拆解分析；也可以从一个想法创建空白项目。</p>
            <label className="btn-primary mt-5 mr-3 inline-block cursor-pointer">
              分析一篇小说
              <input className="hidden" type="file" accept=".txt,.md,text/plain,text/markdown" onChange={(event) => void onPickNovel(event)} />
            </label>
            <button className="btn-soft mt-5 mr-3" onClick={onOpenModels}>先看本地模型</button>
            <button className="btn-soft mt-5" onClick={() => setCreating(true)}>创建空白项目</button>
          </div>
        </section>
      )}

      {creating && (
        <CreateProjectDialog
          onClose={() => setCreating(false)}
          onCreated={async (project) => {
            setCreating(false);
            await onRefresh();
            onOpen(project.id);
          }}
        />
      )}
    </main>
  );
}
