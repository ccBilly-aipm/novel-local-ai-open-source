import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { Chapter, ChapterLoopRunSummary, Character, ModelProvider, Novel, Project, WorldRule } from "../types";

interface Props {
  project: Project;
  novel: Novel;
  providers: ModelProvider[];
  runs: ChapterLoopRunSummary[];
  onNavigate: (view: "chapters" | "creative" | "characters" | "world" | "runs") => void;
  onOpenRun: (runId: string) => void;
}

export default function ProjectOverview({ project, novel, providers, runs, onNavigate, onOpenRun }: Props) {
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [rules, setRules] = useState<WorldRule[]>([]);

  useEffect(() => {
    void Promise.all([
      api<Chapter[]>(`/novels/${novel.id}/chapters`),
      api<Character[]>(`/novels/${novel.id}/characters`),
      api<WorldRule[]>(`/novels/${novel.id}/world-rules`),
    ]).then(([chapterData, characterData, ruleData]) => {
      setChapters(chapterData);
      setCharacters(characterData);
      setRules(ruleData);
    });
  }, [novel.id]);

  const waiting = runs.find((run) => run.status === "waiting");
  const active = runs.find((run) => run.status === "pending" || run.status === "running");
  const failed = runs.find((run) => run.status === "failed");
  const nextChapter = chapters.find((chapter) => !chapter.content.trim()) || chapters[chapters.length - 1];
  const healthyProvider = providers.find((provider) => provider.enabled && provider.last_test_status === "ok");
  const completed = chapters.filter((chapter) => chapter.content.trim()).length;

  const nextAction = waiting
    ? { eyebrow: "Human approval", title: `审批 ${waiting.chapter_title}`, detail: "候选版本和连续性报告已经就绪。批准后才会写入正式正文。", action: () => onOpenRun(waiting.id), label: "查看并审批" }
    : failed
      ? { eyebrow: "Needs attention", title: `诊断 ${failed.chapter_title} 的失败`, detail: `${failed.error_code || "LOOP_FAILED"} · ${failed.error || "查看失败步骤和模型日志"}`, action: () => onOpenRun(failed.id), label: "查看错误" }
      : active
        ? { eyebrow: "Loop running", title: `查看 ${active.chapter_title} 的进度`, detail: "本地模型正在生成或检查，页面会持续读取真实状态。", action: () => onOpenRun(active.id), label: "打开运行详情" }
        : !novel.story_outline.trim()
          ? { eyebrow: "Story foundation", title: "先建立故事设定", detail: "上传一篇参考小说拆解出人物 / 世界观 / 情节，或从一个想法生成故事框架——都在创作中心逐条采纳。", action: () => onNavigate("creative"), label: "打开创作中心" }
          : { eyebrow: "Continue writing", title: nextChapter ? `继续 ${nextChapter.title}` : "创建第一章", detail: "补齐章节目标与大纲，然后启动单章 Loop 生成候选版本。", action: () => onNavigate("chapters"), label: "进入章节工作区" };

  return (
    <main className="mx-auto max-w-7xl p-7">
      <section className="mb-6 grid grid-cols-[1.35fr_0.65fr] gap-5">
        <div className="panel overflow-hidden">
          <div className="bg-ink px-7 py-6 text-white">
            <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-white/40">{nextAction.eyebrow}</div>
            <h1 className="mt-2 font-serif text-3xl font-semibold">{nextAction.title}</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-white/55">{nextAction.detail}</p>
            <button className="mt-5 rounded-xl bg-white px-5 py-2.5 text-sm font-bold text-ink hover:bg-[#f2eadc]" onClick={nextAction.action}>
              {nextAction.label}
            </button>
          </div>
          <div className="grid grid-cols-4 gap-px bg-black/10">
            <div className="bg-white/60 p-4"><div className="text-xs text-black/40">章节进度</div><b className="mt-1 block text-xl">{completed}/{chapters.length}</b></div>
            <button className="bg-white/60 p-4 text-left hover:bg-white" onClick={() => onNavigate("characters")}><div className="text-xs text-black/40">人物</div><b className="mt-1 block text-xl">{characters.length}</b></button>
            <button className="bg-white/60 p-4 text-left hover:bg-white" onClick={() => onNavigate("world")}><div className="text-xs text-black/40">世界规则</div><b className="mt-1 block text-xl">{rules.length}</b></button>
            <button className="bg-white/60 p-4 text-left hover:bg-white" onClick={() => onNavigate("runs")}><div className="text-xs text-black/40">Loop Runs</div><b className="mt-1 block text-xl">{runs.length}</b></button>
          </div>
        </div>
        <section className="panel p-5">
          <div className="label">Model readiness</div>
          <h2 className="font-serif text-xl font-semibold">本地模型状态</h2>
          {healthyProvider ? (
            <div className="mt-4 rounded-xl bg-green-50 p-4">
              <div className="font-semibold text-green-800">{healthyProvider.name}</div>
              <div className="mt-1 truncate text-xs text-green-700">{healthyProvider.model}</div>
              <div className="mt-3 text-xs text-green-700">最近连接测试通过</div>
            </div>
          ) : (
            <div className="mt-4 rounded-xl bg-amber-50 p-4 text-sm text-amber-900">没有最近测试通过的 Provider。生成前先到“本地模型”检查连接。</div>
          )}
          <div className="mt-5 label">Story bible completeness</div>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between"><span>故事总纲</span><b>{novel.story_outline.trim() ? "已填写" : "缺失"}</b></div>
            <div className="flex justify-between"><span>人物卡</span><b>{characters.length}</b></div>
            <div className="flex justify-between"><span>世界规则</span><b>{rules.length}</b></div>
          </div>
        </section>
      </section>

      <div className="grid grid-cols-2 gap-5">
        <section className="panel p-5">
          <div className="mb-4 flex items-center justify-between"><h2 className="font-serif text-xl font-semibold">最近章节</h2><button className="text-xs font-semibold text-moss" onClick={() => onNavigate("chapters")}>查看全部</button></div>
          <div className="space-y-2">
            {[...chapters].reverse().slice(0, 4).map((chapter) => (
              <button key={chapter.id} className="flex w-full items-center justify-between rounded-xl bg-white/55 px-4 py-3 text-left hover:bg-white" onClick={() => onNavigate("chapters")}>
                <span><b className="text-sm">{chapter.title}</b><span className="ml-2 text-xs text-black/35">{chapter.status}</span></span>
                <span className="text-xs text-black/35">{chapter.content.length} 字符</span>
              </button>
            ))}
            {chapters.length === 0 && <div className="rounded-xl border border-dashed border-black/15 p-6 text-center text-sm text-black/40">尚未创建章节。</div>}
          </div>
        </section>
        <section className="panel p-5">
          <div className="mb-4 flex items-center justify-between"><h2 className="font-serif text-xl font-semibold">最近运行</h2><button className="text-xs font-semibold text-moss" onClick={() => onNavigate("runs")}>查看全部</button></div>
          <div className="space-y-2">
            {runs.slice(0, 4).map((run) => (
              <button key={run.id} className="flex w-full items-center justify-between rounded-xl bg-white/55 px-4 py-3 text-left hover:bg-white" onClick={() => onOpenRun(run.id)}>
                <span><b className="text-sm">{run.chapter_title}</b><span className="ml-2 font-mono text-[10px] text-black/35">{run.state}</span></span>
                <span className="rounded-full bg-black/5 px-2 py-1 text-[10px] font-bold">{run.status}</span>
              </button>
            ))}
            {runs.length === 0 && <div className="rounded-xl border border-dashed border-black/15 p-6 text-center text-sm text-black/40">尚未启动 Loop Run。</div>}
          </div>
        </section>
      </div>
    </main>
  );
}
