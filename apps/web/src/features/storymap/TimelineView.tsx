import { useMemo, useRef, useState } from "react";
import type { StoryMap, StoryMapTimelineEvent } from "../../types";
import { useSelection } from "./SelectionContext";
import { useZoom } from "./useZoom";
import { characterColor, foreshadowColor, sameRef, VIZ } from "./theme";

const WIDTH = 900;
const HEIGHT = 520;
const MARGIN = { top: 60, right: 40, bottom: 40, left: 60 };
const LANE_UNANCHORED_Y = MARGIN.top - 24;

// V1 时间线：横轴=章节 order_index 等距格；同章多事件纵向堆叠；事件点按第一主要人物着色。
// 顶部伏笔埋设→回收弧线；「叙事顺序 / 故事顺序」双模式切换。
export default function TimelineView({ data }: { data: StoryMap }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const gRef = useRef<SVGGElement>(null);
  const [mode, setMode] = useState<"narrative" | "story">("narrative");
  const { hovered, selected, setHovered, setSelected } = useSelection();
  useZoom(svgRef, gRef, [0.5, 8], [data.chapters.length]);

  const charIndex = useMemo(() => new Map(data.characters.map((c, i) => [c.id, i])), [data.characters]);
  const orderById = useMemo(() => new Map(data.chapters.map((c) => [c.id, c.order_index])), [data.chapters]);

  const chapters = data.chapters;
  const innerW = WIDTH - MARGIN.left - MARGIN.right;
  const colWidth = chapters.length > 0 ? innerW / chapters.length : innerW;

  function chapterX(orderIndex: number): number {
    const idx = chapters.findIndex((c) => c.order_index === orderIndex);
    const pos = idx >= 0 ? idx : 0;
    return MARGIN.left + pos * colWidth + colWidth / 2;
  }

  // 事件布局：narrative 模式按 chapter_id 列堆叠；story 模式按 story_order 排（无序号灰显沉底）。
  const layout = useMemo(() => {
    const anchored: Array<{ event: StoryMapTimelineEvent; x: number; y: number; faded: boolean }> = [];
    const unanchored: StoryMapTimelineEvent[] = [];
    const stackCount: Record<string, number> = {};

    if (mode === "narrative") {
      for (const ev of data.timeline_events) {
        if (!ev.chapter_id || !orderById.has(ev.chapter_id)) {
          unanchored.push(ev);
          continue;
        }
        const order = orderById.get(ev.chapter_id)!;
        const key = String(order);
        const stack = stackCount[key] || 0;
        stackCount[key] = stack + 1;
        anchored.push({ event: ev, x: chapterX(order), y: MARGIN.top + 40 + stack * 34, faded: false });
      }
    } else {
      // story 模式：有 story_order 的按序号横向排布，无序号的灰显沉底。
      const withOrder = data.timeline_events.filter((e) => e.story_order != null).sort((a, b) => (a.story_order! - b.story_order!));
      const without = data.timeline_events.filter((e) => e.story_order == null);
      withOrder.forEach((ev, i) => {
        const x = MARGIN.left + (withOrder.length > 1 ? (i / (withOrder.length - 1)) * innerW : innerW / 2);
        anchored.push({ event: ev, x, y: MARGIN.top + 60, faded: false });
      });
      without.forEach((ev, i) => {
        const x = MARGIN.left + (without.length > 1 ? (i / (without.length - 1)) * innerW : innerW / 2);
        anchored.push({ event: ev, x, y: HEIGHT - MARGIN.bottom - 20, faded: true });
      });
    }
    return { anchored, unanchored };
  }, [data.timeline_events, mode, orderById, colWidth]); // eslint-disable-line react-hooks/exhaustive-deps

  const latestOrder = chapters.length ? Math.max(...chapters.map((c) => c.order_index)) : 0;

  function eventColor(ev: StoryMapTimelineEvent): string {
    const first = ev.character_ids[0];
    if (first && charIndex.has(first)) return characterColor(first, charIndex.get(first)!);
    return VIZ.muted;
  }

  function isHl(kind: "event" | "chapter" | "character", id: string): boolean {
    const active = hovered || selected;
    if (!active) return false;
    if (active.kind === kind && active.id === id) return true;
    // 联动：hover 人物 → 高亮其事件
    if (active.kind === "character" && kind === "event") {
      const ev = data.timeline_events.find((e) => e.id === id);
      return !!ev && ev.character_ids.includes(active.id);
    }
    return false;
  }

  return (
    <div className="panel overflow-hidden">
      <div className="flex items-center justify-between border-b border-black/10 px-4 py-2">
        <div className="flex gap-1 rounded-lg border border-black/10 bg-white/60 p-0.5 text-xs">
          <button className={`rounded-md px-3 py-1 font-semibold ${mode === "narrative" ? "bg-ink text-white" : "text-black/50"}`} onClick={() => setMode("narrative")}>
            叙事顺序
          </button>
          <button className={`rounded-md px-3 py-1 font-semibold ${mode === "story" ? "bg-ink text-white" : "text-black/50"}`} onClick={() => setMode("story")}>
            故事顺序
          </button>
        </div>
        <span className="text-xs text-black/40">
          {mode === "story" ? "按 story_order 重排；灰点=无故事序号" : "横轴=章节顺序"}
        </span>
      </div>
      <svg ref={svgRef} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full" style={{ height: HEIGHT, cursor: "grab" }}>
        <g ref={gRef}>
          {/* 章节主轴 + 列 */}
          {mode === "narrative" && (
            <>
              <line x1={MARGIN.left} y1={HEIGHT - MARGIN.bottom} x2={WIDTH - MARGIN.right} y2={HEIGHT - MARGIN.bottom} stroke={VIZ.grid} />
              {chapters.map((c) => (
                <g key={c.id}>
                  <line x1={chapterX(c.order_index)} y1={MARGIN.top} x2={chapterX(c.order_index)} y2={HEIGHT - MARGIN.bottom} stroke={VIZ.grid} strokeDasharray="2 4" />
                  <text
                    x={chapterX(c.order_index)}
                    y={HEIGHT - MARGIN.bottom + 16}
                    textAnchor="middle"
                    className="cursor-pointer select-none"
                    style={{ fontSize: 10, fontFamily: "ui-monospace, monospace", fill: sameRef(selected, { kind: "chapter", id: c.id }) ? VIZ.ink : "rgba(0,0,0,0.5)" }}
                    onMouseEnter={() => setHovered({ kind: "chapter", id: c.id })}
                    onMouseLeave={() => setHovered(null)}
                    onClick={() => setSelected({ kind: "chapter", id: c.id })}
                  >
                    第{c.order_index}章
                  </text>
                </g>
              ))}
            </>
          )}

          {/* 顶部伏笔弧线层 */}
          {mode === "narrative" &&
            data.foreshadowing.map((f) => {
              const plantedOrder = f.planted_chapter_id ? orderById.get(f.planted_chapter_id) : undefined;
              if (plantedOrder == null) return null;
              const x1 = chapterX(plantedOrder);
              const resolvedOrder = f.resolved_chapter_id ? orderById.get(f.resolved_chapter_id) : undefined;
              const overdue = f.status !== "resolved" && latestOrder - plantedOrder > 20;
              const color = foreshadowColor(f.status, overdue);
              const x2 = resolvedOrder != null ? chapterX(resolvedOrder) : chapterX(latestOrder);
              const midY = LANE_UNANCHORED_Y - 26;
              const path = `M ${x1} ${LANE_UNANCHORED_Y} Q ${(x1 + x2) / 2} ${midY} ${x2} ${LANE_UNANCHORED_Y}`;
              return (
                <path
                  key={f.id}
                  d={path}
                  fill="none"
                  stroke={color}
                  strokeWidth={sameRef(hovered, { kind: "foreshadow", id: f.id }) ? 2.5 : 1.5}
                  strokeDasharray={f.status === "resolved" ? undefined : "4 3"}
                  opacity={0.85}
                  style={{ cursor: "pointer" }}
                  onMouseEnter={() => setHovered({ kind: "foreshadow", id: f.id })}
                  onMouseLeave={() => setHovered(null)}
                  onClick={() => setSelected({ kind: "foreshadow", id: f.id })}
                >
                  <title>{f.description}{overdue ? "（超期未回收）" : ""}</title>
                </path>
              );
            })}

          {/* 未锚定泳道标签 */}
          {layout.unanchored.length > 0 && (
            <text x={MARGIN.left} y={LANE_UNANCHORED_Y + 4} style={{ fontSize: 10, fill: "rgba(0,0,0,0.4)" }}>
              未锚定 →
            </text>
          )}
          {layout.unanchored.map((ev, i) => (
            <EventDot
              key={ev.id}
              cx={MARGIN.left + 60 + i * 26}
              cy={LANE_UNANCHORED_Y}
              color={VIZ.muted}
              label={ev.title}
              hl={isHl("event", ev.id)}
              faded={false}
              onEnter={() => setHovered({ kind: "event", id: ev.id })}
              onLeave={() => setHovered(null)}
              onClick={() => setSelected({ kind: "event", id: ev.id })}
            />
          ))}

          {/* 事件点 */}
          {layout.anchored.map(({ event, x, y, faded }) => (
            <EventDot
              key={event.id}
              cx={x}
              cy={y}
              color={eventColor(event)}
              label={event.title + (event.story_time ? ` · ${event.story_time}` : "")}
              hl={isHl("event", event.id)}
              faded={faded}
              onEnter={() => setHovered({ kind: "event", id: event.id })}
              onLeave={() => setHovered(null)}
              onClick={() => setSelected({ kind: "event", id: event.id })}
            />
          ))}
        </g>
      </svg>
    </div>
  );
}

function EventDot({
  cx,
  cy,
  color,
  label,
  hl,
  faded,
  onEnter,
  onLeave,
  onClick,
}: {
  cx: number;
  cy: number;
  color: string;
  label: string;
  hl: boolean;
  faded: boolean;
  onEnter: () => void;
  onLeave: () => void;
  onClick: () => void;
}) {
  return (
    <g
      className="storymap-node"
      style={{ cursor: "pointer", opacity: faded ? 0.4 : 1 }}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      onClick={onClick}
    >
      {hl && <circle cx={cx} cy={cy} r={11} fill={color} opacity={0.2} className="storymap-halo" />}
      <circle cx={cx} cy={cy} r={hl ? 7 : 5} fill={color} stroke="#fff" strokeWidth={1} className="storymap-dot" />
      <text x={cx + 9} y={cy + 3} style={{ fontSize: 9, fill: "rgba(0,0,0,0.6)", pointerEvents: "none" }}>
        {label.slice(0, 14)}
      </text>
    </g>
  );
}
