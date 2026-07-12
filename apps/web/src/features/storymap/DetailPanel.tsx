import { useState } from "react";
import { api } from "../../services/api";
import type {
  StoryMap,
  StoryMapCharacter,
  StoryMapForeshadowing,
  StoryMapPlotThread,
  StoryMapTimelineEvent,
} from "../../types";
import { useSelection } from "./SelectionContext";
import type { EntityKind } from "./theme";
import EntityForm, { EntityFormKind } from "./EntityForm";
import type { ViewTab } from "./StoryMapPage";

interface Props {
  data: StoryMap;
  projectId: string;
  view: ViewTab;
  onChanged: () => void;
  onJump: (view: ViewTab) => void;
}

const DELETE_PATH: Partial<Record<EntityKind, string>> = {
  event: "/timeline-events",
  thread: "/plot-threads",
  foreshadow: "/foreshadowing",
};

// 常驻右侧详情面板：无选中显示当前视图统计摘要；选中显示实体卡 + 内联编辑 + 删除 + 关联跳转。
export default function DetailPanel({ data, view, onChanged, onJump }: Props) {
  const { selected, setSelected } = useSelection();
  const [editing, setEditing] = useState(false);

  if (!selected) {
    return <SummaryCard data={data} view={view} />;
  }

  const charById = new Map(data.characters.map((c) => [c.id, c]));
  const chapterById = new Map(data.chapters.map((c) => [c.id, c]));

  if (selected.kind === "character") {
    const ch = charById.get(selected.id);
    if (!ch) return <SummaryCard data={data} view={view} />;
    return <CharacterCard character={ch} data={data} onJump={onJump} />;
  }
  if (selected.kind === "chapter") {
    const ch = chapterById.get(selected.id);
    if (!ch) return <SummaryCard data={data} view={view} />;
    return (
      <Panel title="章节">
        <h4 className="font-serif text-lg font-semibold">
          第{ch.order_index}章 · {ch.title}
        </h4>
        <Meta label="状态" value={ch.status} />
        <Meta label="字数" value={String(ch.word_count)} />
        {ch.summary && <p className="mt-2 text-sm leading-6 text-black/60">{ch.summary}</p>}
      </Panel>
    );
  }

  // event / thread / foreshadow → 可编辑实体
  const entity =
    selected.kind === "event"
      ? data.timeline_events.find((e) => e.id === selected.id)
      : selected.kind === "thread"
        ? data.plot_threads.find((t) => t.id === selected.id)
        : data.foreshadowing.find((f) => f.id === selected.id);

  if (!entity) return <SummaryCard data={data} view={view} />;

  const formKind: EntityFormKind =
    selected.kind === "event" ? "event" : selected.kind === "thread" ? "thread" : "foreshadow";

  async function remove() {
    if (!selected) return;
    const path = DELETE_PATH[selected.kind];
    if (!path) return;
    if (!window.confirm("确认删除该条目？此操作会从故事地图移除它。")) return;
    await api(`${path}/${selected.id}`, { method: "DELETE" });
    setSelected(null);
    onChanged();
  }

  if (editing) {
    return (
      <Panel title="编辑">
        <EntityForm
          kind={formKind}
          novelId={""}
          chapters={data.chapters}
          editId={selected.id}
          initial={entity as unknown as Record<string, unknown>}
          onDone={() => {
            setEditing(false);
            onChanged();
          }}
          onCancel={() => setEditing(false)}
        />
      </Panel>
    );
  }

  return (
    <Panel title={formKind === "event" ? "事件" : formKind === "thread" ? "情节线" : "伏笔"}>
      {selected.kind === "event" && (
        <EventDetail event={entity as StoryMapTimelineEvent} data={data} onJump={onJump} />
      )}
      {selected.kind === "thread" && <ThreadDetail thread={entity as StoryMapPlotThread} data={data} onJump={onJump} />}
      {selected.kind === "foreshadow" && (
        <ForeshadowDetail fore={entity as StoryMapForeshadowing} data={data} onJump={onJump} />
      )}
      <div className="mt-4 flex gap-2 border-t border-black/10 pt-3">
        <button className="btn-soft flex-1" onClick={() => setEditing(true)}>
          编辑
        </button>
        <button className="btn-soft flex-1 text-rust" onClick={() => void remove()}>
          删除
        </button>
      </div>
    </Panel>
  );
}

// ───────────────────────── 子组件 ─────────────────────────

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  const { setSelected } = useSelection();
  return (
    <div className="panel sticky top-4 p-5">
      <div className="mb-2 flex items-center justify-between">
        <span className="label mb-0">{title}</span>
        <button className="text-xs text-black/40 hover:text-black" onClick={() => setSelected(null)}>
          ✕ 清除
        </button>
      </div>
      {children}
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="mt-1 flex gap-2 text-xs">
      <span className="text-black/40">{label}</span>
      <span className="font-mono text-black/70">{value}</span>
    </div>
  );
}

function Chip({ label, onClick }: { label: string; onClick?: () => void }) {
  return (
    <button
      className="rounded-lg border border-black/10 bg-white/70 px-2 py-1 text-xs hover:bg-white disabled:cursor-default"
      onClick={onClick}
      disabled={!onClick}
    >
      {label}
    </button>
  );
}

function chapterLabel(data: StoryMap, id: string | null): string {
  if (!id) return "未锚定";
  const ch = data.chapters.find((c) => c.id === id);
  return ch ? `第${ch.order_index}章` : "未知章节";
}

function EventDetail({
  event,
  data,
  onJump,
}: {
  event: StoryMapTimelineEvent;
  data: StoryMap;
  onJump: (v: ViewTab) => void;
}) {
  const { setSelected } = useSelection();
  const charById = new Map(data.characters.map((c) => [c.id, c]));
  return (
    <>
      <h4 className="font-serif text-lg font-semibold">{event.title}</h4>
      {event.story_time && <Meta label="故事时间" value={event.story_time} />}
      {event.story_order != null && <Meta label="故事顺序" value={String(event.story_order)} />}
      <Meta label="锚定章节" value={chapterLabel(data, event.chapter_id)} />
      {event.description && <p className="mt-2 text-sm leading-6 text-black/60">{event.description}</p>}
      {event.character_ids.length > 0 && (
        <div className="mt-3">
          <span className="label">涉及人物</span>
          <div className="flex flex-wrap gap-1">
            {event.character_ids.map((cid) => {
              const c = charById.get(cid);
              return (
                <Chip
                  key={cid}
                  label={c ? c.name : cid.slice(0, 6)}
                  onClick={c ? () => { setSelected({ kind: "character", id: cid }); onJump("characters"); } : undefined}
                />
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}

function ThreadDetail({ thread, data, onJump }: { thread: StoryMapPlotThread; data: StoryMap; onJump: (v: ViewTab) => void }) {
  const { setSelected } = useSelection();
  return (
    <>
      <h4 className="font-serif text-lg font-semibold">{thread.name}</h4>
      <Meta label="状态" value={thread.status} />
      {thread.description && <p className="mt-2 text-sm leading-6 text-black/60">{thread.description}</p>}
      {thread.resolution && <p className="mt-1 text-xs text-black/45">收束：{thread.resolution}</p>}
      {thread.related_chapter_ids.length > 0 && (
        <div className="mt-3">
          <span className="label">涉及章节</span>
          <div className="flex flex-wrap gap-1">
            {thread.related_chapter_ids.map((cid) => (
              <Chip
                key={cid}
                label={chapterLabel(data, cid)}
                onClick={() => { setSelected({ kind: "chapter", id: cid }); onJump("timeline"); }}
              />
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function ForeshadowDetail({ fore, data, onJump }: { fore: StoryMapForeshadowing; data: StoryMap; onJump: (v: ViewTab) => void }) {
  const { setSelected } = useSelection();
  return (
    <>
      <h4 className="font-serif text-lg font-semibold">伏笔</h4>
      <p className="mt-1 text-sm leading-6 text-black/70">{fore.description}</p>
      <Meta label="状态" value={fore.status} />
      <div className="mt-2 flex flex-wrap gap-1">
        {fore.planted_chapter_id && (
          <Chip label={`埋设 ${chapterLabel(data, fore.planted_chapter_id)}`} onClick={() => { setSelected({ kind: "chapter", id: fore.planted_chapter_id! }); onJump("timeline"); }} />
        )}
        {fore.resolved_chapter_id && (
          <Chip label={`回收 ${chapterLabel(data, fore.resolved_chapter_id)}`} onClick={() => { setSelected({ kind: "chapter", id: fore.resolved_chapter_id! }); onJump("timeline"); }} />
        )}
      </div>
      {fore.notes && <p className="mt-2 text-xs text-black/45">{fore.notes}</p>}
    </>
  );
}

function CharacterCard({ character, data, onJump }: { character: StoryMapCharacter; data: StoryMap; onJump: (v: ViewTab) => void }) {
  const { setSelected } = useSelection();
  const events = data.timeline_events.filter((e) => e.character_ids.includes(character.id));
  return (
    <Panel title="人物">
      <h4 className="font-serif text-lg font-semibold">{character.name}</h4>
      {character.role && <Meta label="角色" value={character.role} />}
      <Meta label="出场章节" value={character.presence_chapters.map((n) => `第${n}章`).join("、") || "—"} />
      {character.arc && <p className="mt-2 text-sm leading-6 text-black/60">{character.arc}</p>}
      {events.length > 0 && (
        <div className="mt-3">
          <span className="label">相关事件（点击跳时间线）</span>
          <div className="space-y-1">
            {events.map((e) => (
              <button
                key={e.id}
                className="block w-full truncate rounded-lg border border-black/10 bg-white/60 px-2 py-1 text-left text-xs hover:bg-white"
                onClick={() => { setSelected({ kind: "event", id: e.id }); onJump("timeline"); }}
              >
                {e.title}
              </button>
            ))}
          </div>
        </div>
      )}
    </Panel>
  );
}

function SummaryCard({ data, view }: { data: StoryMap; view: ViewTab }) {
  const counts = data.stats.foreshadow_counts;
  return (
    <div className="panel sticky top-4 p-5">
      <span className="label">当前视图摘要</span>
      <div className="grid grid-cols-2 gap-3">
        <Stat label="事件" value={data.timeline_events.length} />
        <Stat label="人物" value={data.characters.length} />
        <Stat label="情节线" value={data.plot_threads.length} />
        <Stat label="伏笔" value={data.foreshadowing.length} />
      </div>
      <div className="mt-4 rounded-xl border border-black/10 bg-white/50 p-3 text-xs">
        <div className="mb-1 font-semibold text-black/60">伏笔健康度</div>
        <div className="flex gap-3">
          <span style={{ color: "#b45309" }}>开放 {counts.open}</span>
          <span style={{ color: "#38564a" }}>已回收 {counts.resolved}</span>
          <span className={counts.overdue > 0 ? "font-bold" : ""} style={{ color: "#b3261e" }}>
            超期 {counts.overdue}
          </span>
        </div>
      </div>
      <p className="mt-3 text-xs text-black/40">
        在{view === "timeline" ? "时间线" : view === "characters" ? "人物网络" : view === "threads" ? "故事线" : "仪表盘"}中悬停或点击元素查看详情。
      </p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-black/10 bg-white/50 p-3 text-center">
      <div className="font-mono text-2xl font-semibold">{value}</div>
      <div className="text-xs text-black/45">{label}</div>
    </div>
  );
}
