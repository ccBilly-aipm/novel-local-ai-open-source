import type { ChapterLoopRunSummary, ModelProvider, Novel, Project } from "../types";
import ChapterWorkspaceV2 from "../features/chapters/ChapterWorkspaceV2";
import RunDetailPage from "../features/runs/RunDetailPage";
import RunListPage from "../features/runs/RunListPage";
import CharacterCards from "./CharacterCards";
import CreativeStudio from "./CreativeStudio";
import ProjectOverview from "./ProjectOverview";
import Workspace from "./Workspace";
import Worldbuilding from "./Worldbuilding";
import StoryMapPage from "../features/storymap/StoryMapPage";

export type ProjectView = "overview" | "chapters" | "storymap" | "creative" | "characters" | "world" | "runs" | "advanced";

interface Props {
  project: Project;
  novel: Novel;
  view: ProjectView;
  runId: string | null;
  providers: ModelProvider[];
  runs: ChapterLoopRunSummary[];
  onNovelChange: (novel: Novel) => void;
  onNavigate: (view: ProjectView) => void;
  onOpenRun: (runId: string) => void;
  onRefresh: () => Promise<void>;
}

const tabs: Array<[ProjectView, string]> = [
  ["overview", "总览"],
  ["chapters", "章节"],
  ["storymap", "故事地图"],
  ["creative", "创作中心"],
  ["characters", "人物"],
  ["world", "设定"],
  ["runs", "Loop Runs"],
  // 「高级功能」(legacy WritingTask，会直接改正文) 从主导航收起，仍可经 URL /…/advanced 访问。
];

export default function ProjectWorkspaceShell({
  project,
  novel,
  view,
  runId,
  providers,
  runs,
  onNovelChange,
  onNavigate,
  onOpenRun,
  onRefresh,
}: Props) {
  return (
    <div>
      <header className="flex h-[78px] items-center border-b border-black/10 bg-[#f5f1e8]/90 px-6 backdrop-blur">
        <div className="mr-9 min-w-48">
          <div className="text-[10px] uppercase tracking-[0.2em] text-black/35">{project.name}</div>
          <div className="truncate font-serif text-lg font-semibold">{novel.title}</div>
        </div>
        <nav className="flex h-full items-center gap-1">
          {tabs.map(([key, label]) => (
            <button
              key={key}
              className={`relative h-full px-3 text-sm font-semibold ${view === key ? "text-moss" : "text-black/45 hover:text-black"}`}
              onClick={() => onNavigate(key)}
            >
              {label}
              {key === "runs" && runs.some((run) => run.status === "waiting") && <span className="ml-1.5 h-2 w-2 rounded-full bg-rust inline-block" />}
              {view === key && <span className="absolute inset-x-2 bottom-0 h-0.5 bg-moss" />}
            </button>
          ))}
        </nav>
      </header>

      {runId ? (
        <RunDetailPage
          projectId={project.id}
          runId={runId}
          onBack={() => onNavigate("runs")}
          onChanged={onRefresh}
          onOpenRun={onOpenRun}
        />
      ) : view === "overview" ? (
        <ProjectOverview project={project} novel={novel} providers={providers} runs={runs} onNavigate={onNavigate} onOpenRun={onOpenRun} />
      ) : view === "chapters" ? (
        <ChapterWorkspaceV2 projectId={project.id} novel={novel} providers={providers} runs={runs} onOpenRun={onOpenRun} onRunsChanged={onRefresh} />
      ) : view === "storymap" ? (
        <StoryMapPage projectId={project.id} novel={novel} providers={providers} />
      ) : view === "creative" ? (
        <CreativeStudio novel={novel} onNovelChange={onNovelChange} onOpenChapters={() => onNavigate("chapters")} />
      ) : view === "characters" ? (
        <CharacterCards novelId={novel.id} />
      ) : view === "world" ? (
        <Worldbuilding novelId={novel.id} />
      ) : view === "runs" ? (
        <RunListPage
          projectId={project.id}
          runs={runs}
          title={`${novel.title} · Loop Runs`}
          onOpen={(run) => onOpenRun(run.id)}
          onOpenRunId={onOpenRun}
        />
      ) : (
        <div>
          <div className="border-b border-amber-200 bg-amber-50 px-6 py-3 text-xs text-amber-900">
            Legacy / Advanced：以下工具沿用旧 WritingTask 与 <code>/api/chapters/{"{id}"}/generate</code>，可能直接更新章节正文。主流程请使用“章节”中的单章 Loop。
          </div>
          <Workspace novel={novel} onNovelChange={onNovelChange} />
        </div>
      )}
    </div>
  );
}
