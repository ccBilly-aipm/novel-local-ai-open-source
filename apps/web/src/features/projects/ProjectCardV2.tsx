import { useEffect, useMemo, useState } from "react";
import { api } from "../../services/api";
import type { Chapter, ChapterLoopRunSummary, Project } from "../../types";

interface Props {
  project: Project;
  runs: ChapterLoopRunSummary[];
  onOpen: (projectId: string) => void;
  onOpenRun: (run: ChapterLoopRunSummary) => void;
  onDelete: (projectId: string) => Promise<void>;
}

export default function ProjectCardV2({ project, runs, onOpen, onOpenRun, onDelete }: Props) {
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [novelTitle, setNovelTitle] = useState("");
  const projectRuns = useMemo(() => runs.filter((run) => run.project_id === project.id), [runs, project.id]);
  const waiting = projectRuns.find((run) => run.status === "waiting");
  const active = projectRuns.find((run) => run.status === "running" || run.status === "pending");
  const failed = projectRuns.find((run) => run.status === "failed");
  const priorityRun = waiting || active || failed;

  useEffect(() => {
    void (async () => {
      const detail = await api<Project>(`/projects/${project.id}`);
      const novel = detail.novels?.[0];
      setNovelTitle(novel?.title || project.name);
      if (novel) setChapters(await api<Chapter[]>(`/novels/${novel.id}/chapters`));
    })().catch(() => undefined);
  }, [project.id, project.updated_at]);

  const completed = chapters.filter((chapter) => chapter.content.trim()).length;
  const latestChapter = [...chapters].reverse().find((chapter) => chapter.content.trim()) || chapters[0];
  const waitingCount = projectRuns.filter((run) => run.status === "waiting").length;

  return (
    <article className="panel group flex min-h-72 flex-col p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-moss">Local project</div>
          <h3 className="mt-2 font-serif text-2xl font-semibold group-hover:text-moss">{project.name}</h3>
          <p className="mt-1 text-sm text-black/45">{novelTitle}</p>
        </div>
        <details className="relative">
          <summary className="cursor-pointer list-none rounded-lg px-2 py-1 text-black/35 hover:bg-black/5">•••</summary>
          <div className="absolute right-0 z-10 mt-1 w-32 rounded-xl border border-black/10 bg-white p-1 shadow-panel">
            <button className="w-full rounded-lg px-3 py-2 text-left text-xs text-red-700 hover:bg-red-50" onClick={() => void onDelete(project.id)}>
              删除项目
            </button>
          </div>
        </details>
      </div>

      <p className="mt-5 line-clamp-2 min-h-10 text-sm leading-5 text-black/50">
        {project.description || "尚未填写项目说明"}
      </p>
      <div className="mt-5 grid grid-cols-3 gap-2 text-center text-xs">
        <div className="rounded-xl bg-black/[0.035] p-2"><b className="block text-base">{chapters.length}</b>章节</div>
        <div className="rounded-xl bg-black/[0.035] p-2"><b className="block text-base">{completed}</b>有正文</div>
        <div className="rounded-xl bg-black/[0.035] p-2"><b className="block text-base">{projectRuns.length}</b>Loop</div>
      </div>
      <div className="mt-3 flex justify-between text-xs text-black/40">
        <span>最近章节：{latestChapter?.title || "尚未创建"}</span>
        <span>待审批 {waitingCount}</span>
      </div>

      <div className="mt-auto pt-5">
        {(waiting || active || failed) && (
          <div className={`mb-3 rounded-xl px-3 py-2 text-xs ${
            waiting ? "bg-amber-50 text-amber-900" : active ? "bg-blue-50 text-blue-800" : "bg-red-50 text-red-700"
          }`}>
            {waiting ? `${waiting.chapter_title} 有草稿待审批` : active ? `${active.chapter_title} 正在运行` : `${failed?.chapter_title} 运行失败`}
          </div>
        )}
        <button
          className="btn-primary w-full"
          onClick={() => priorityRun ? onOpenRun(priorityRun) : onOpen(project.id)}
        >
          {waiting ? "审批草稿" : active ? "查看运行进度" : latestChapter ? "继续写作" : "进入项目总览"}
        </button>
      </div>
    </article>
  );
}
