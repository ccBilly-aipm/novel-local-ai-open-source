import { useMemo, useState } from "react";
import type { ActivityItem } from "../../types";

interface Props {
  activity: ActivityItem[];
  onOpen: (item: ActivityItem) => void;
}

const kindFilters: ReadonlyArray<[string, string]> = [
  ["all", "全部类型"],
  ["loop", "章节生成"],
  ["multi_chapter", "多章生产线"],
  ["deconstruction", "拆解小说"],
  ["creative", "创作中心"],
];

const statusFilters: ReadonlyArray<[string, string]> = [
  ["all", "全部状态"],
  ["running", "运行中"],
  ["waiting", "待审批"],
  ["paused", "暂停"],
  ["failed", "失败"],
  ["done", "已完成"],
];

const kindLabels: Record<string, string> = {
  loop: "章节生成",
  multi_chapter: "多章生产线",
  deconstruction: "拆解小说",
  creative: "创作中心",
};

function statusCategory(status: string): string {
  if (status === "failed") return "failed";
  if (status === "waiting") return "waiting";
  if (status === "paused") return "paused";
  if (["committed", "approved", "completed", "memory_updated", "rejected", "stopped", "success", "done", "ok"].includes(status)) return "done";
  return "running";
}

function statusBadgeClass(status: string): string {
  switch (statusCategory(status)) {
    case "failed":
      return "bg-red-100 text-red-700";
    case "waiting":
    case "paused":
      return "bg-amber-100 text-amber-800";
    case "done":
      return "bg-green-100 text-green-700";
    default:
      return "bg-blue-100 text-blue-700";
  }
}

interface Group {
  key: string;
  items: ActivityItem[];
}

// 同一任务归组：章节 Loop 按 (小说, 章节) 折叠；其余类型按 (类型, 小说, 标题) 折叠，
// 这样反复跑的「拆解参考小说 / 拆解·人物」会合并到一栏，不再因为时间不同铺满整页。
function groupKeyOf(item: ActivityItem): string {
  if (item.kind === "loop" && item.chapter_id) {
    return `loop:${item.novel_id}:${item.chapter_id}`;
  }
  const scope = item.novel_id || item.project_id || item.id;
  return `${item.kind}:${scope}:${item.title}`;
}

// 固定列宽 → 每一行的「状态」列处在相同的 x 与相同的宽度，徽标在列内居中，
// 因此所有 Running / Completed 徽标共享同一条垂直中轴线；同时长文本在各自列内截断，不会被右侧徽标遮挡。
function ActivityRow({ item, onOpen }: { item: ActivityItem; onOpen: (item: ActivityItem) => void }) {
  const isFailed = statusCategory(item.status) === "failed";
  return (
    <button
      className="grid w-full grid-cols-[80px_minmax(0,1.7fr)_minmax(0,1fr)_120px_172px] items-center gap-3 px-4 py-4 text-left hover:bg-white/60"
      onClick={() => onOpen(item)}
    >
      <span className="w-fit justify-self-start whitespace-nowrap rounded-full bg-black/5 px-2 py-1 text-[10px] font-bold text-black/55">
        {kindLabels[item.kind] || item.kind}
      </span>
      <div className="min-w-0">
        <b className="block truncate">{item.title}</b>
        <div className="block truncate text-xs text-black/40">{item.subtitle || "—"}</div>
      </div>
      <div className="block min-w-0 truncate font-mono text-[10px] text-black/45">
        {item.state}
        {isFailed && item.error_code && <span className="ml-1 text-red-700">{item.error_code}</span>}
      </div>
      <span className={`w-fit justify-self-center whitespace-nowrap rounded-full px-2.5 py-1 text-center text-[10px] font-bold ${statusBadgeClass(item.status)}`}>
        {item.status}
      </span>
      <span className="justify-self-end whitespace-nowrap text-right text-xs text-black/35">
        {new Date(item.updated_at).toLocaleString()}
      </span>
    </button>
  );
}

export default function ActivityListPage({ activity, onOpen }: Props) {
  const [kind, setKind] = useState("all");
  const [status, setStatus] = useState("all");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggle(key: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const groups = useMemo<Group[]>(() => {
    const filtered = activity.filter(
      (item) => (kind === "all" || item.kind === kind) && (status === "all" || statusCategory(item.status) === status),
    );
    // activity 已按 updated_at 倒序，组内首条即最新。
    const result: Group[] = [];
    const index = new Map<string, number>();
    for (const item of filtered) {
      const key = groupKeyOf(item);
      const existing = index.get(key);
      if (existing !== undefined) {
        result[existing].items.push(item);
      } else {
        index.set(key, result.length);
        result.push({ key, items: [item] });
      }
    }
    return result;
  }, [activity, kind, status]);

  return (
    <main className="mx-auto max-w-7xl p-8">
      <div className="mb-7">
        <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-rust">Activity</div>
        <h1 className="mt-1 font-serif text-4xl font-semibold">运行记录</h1>
        <p className="mt-2 text-sm text-black/50">
          章节生成、多章生产线、拆解参考小说、创作中心的每一次模型调用都在这里。同一任务的多次运行已折叠成一栏，置顶最新一次，点左侧三角展开历史。
        </p>
      </div>

      <div className="mb-3 flex flex-wrap gap-2">
        {kindFilters.map(([key, label]) => (
          <button
            key={key}
            className={`rounded-full px-4 py-2 text-xs font-semibold ${kind === key ? "bg-ink text-white" : "bg-white/60 text-black/50"}`}
            onClick={() => setKind(key)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="mb-5 flex flex-wrap gap-2">
        {statusFilters.map(([key, label]) => (
          <button
            key={key}
            className={`rounded-full px-4 py-2 text-xs font-semibold ${status === key ? "bg-moss text-white" : "bg-white/60 text-black/50"}`}
            onClick={() => setStatus(key)}
          >
            {label}
          </button>
        ))}
      </div>

      <section className="panel overflow-hidden">
        {groups.map((group) => {
          const [latest, ...history] = group.items;
          const hasHistory = history.length > 0;
          const isOpen = expanded.has(group.key);
          return (
            <div key={group.key} className="border-b border-black/5 last:border-0">
              <div className="flex items-stretch">
                {hasHistory ? (
                  <button
                    className="flex w-10 shrink-0 flex-col items-center justify-center gap-0.5 border-r border-black/5 text-black/35 hover:bg-black/[0.03] hover:text-black/60"
                    onClick={() => toggle(group.key)}
                    title={isOpen ? "收起历史" : `展开本组 ${group.items.length} 次运行`}
                  >
                    <span className={`text-[11px] leading-none transition-transform ${isOpen ? "rotate-90" : ""}`}>▸</span>
                    <span className="text-[9px] font-bold leading-none">{group.items.length}</span>
                  </button>
                ) : (
                  <span className="w-10 shrink-0 border-r border-transparent" />
                )}
                <div className="min-w-0 flex-1">
                  <ActivityRow item={latest} onOpen={onOpen} />
                </div>
              </div>
              {hasHistory && isOpen && (
                <div className="border-t border-black/5 bg-black/[0.015]">
                  <div className="py-1.5 pl-14 text-[11px] text-black/40">同类共 {group.items.length} 次，以下为历史运行：</div>
                  {history.map((item) => (
                    <div key={item.id} className="flex items-stretch opacity-75">
                      <span className="w-10 shrink-0 border-r border-black/5" />
                      <div className="min-w-0 flex-1">
                        <ActivityRow item={item} onOpen={onOpen} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {groups.length === 0 && <div className="p-12 text-center text-sm text-black/40">此筛选条件下没有记录。</div>}
      </section>
    </main>
  );
}
