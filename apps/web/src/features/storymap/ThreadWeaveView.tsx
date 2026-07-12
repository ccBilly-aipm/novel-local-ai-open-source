import { useMemo, useRef, useState } from "react";
import { line as d3line, curveMonotoneX } from "d3-shape";
import type { StoryMap } from "../../types";
import { useSelection } from "./SelectionContext";
import { useZoom } from "./useZoom";
import { characterColor, foreshadowColor, sameRef, VIZ } from "./theme";

const WIDTH = 900;
const HEIGHT = 520;
const MARGIN = { top: 40, right: 30, bottom: 30, left: 140 };
const ROW_H = 42;

// V3 故事线织线图：泳道网格（行=PlotThread + 独立伏笔行，列=章节）；thread 在其
// related_chapter_ids 打结点，结点间 curveMonotoneX 连线；伏笔菱形挂对应列。
export default function ThreadWeaveView({ data }: { data: StoryMap }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const gRef = useRef<SVGGElement>(null);
  const { hovered, selected, setHovered, setSelected } = useSelection();
  const [hoverChapter, setHoverChapter] = useState<string | null>(null);
  useZoom(svgRef, gRef, [0.5, 6], [data.plot_threads.length, data.chapters.length]);

  const chapters = data.chapters;
  const orderById = useMemo(() => new Map(chapters.map((c) => [c.id, c.order_index])), [chapters]);
  const innerW = WIDTH - MARGIN.left - MARGIN.right;
  const colWidth = chapters.length > 0 ? innerW / chapters.length : innerW;

  function colX(chapterId: string): number {
    const idx = chapters.findIndex((c) => c.id === chapterId);
    return MARGIN.left + (idx >= 0 ? idx : 0) * colWidth + colWidth / 2;
  }

  const threads = data.plot_threads;
  const threadRowY = (i: number) => MARGIN.top + 20 + i * ROW_H;
  const independentRowY = MARGIN.top + 20 + threads.length * ROW_H;

  const latestOrder = chapters.length ? Math.max(...chapters.map((c) => c.order_index)) : 0;

  const curve = d3line<[number, number]>()
    .x((d) => d[0])
    .y((d) => d[1])
    .curve(curveMonotoneX);

  const active = hovered || selected;

  return (
    <div className="panel overflow-hidden">
      <svg ref={svgRef} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full" style={{ height: HEIGHT, cursor: "grab" }}>
        <g ref={gRef}>
          {/* 列头（章节）+ 悬停淡金背景条 */}
          {chapters.map((c) => (
            <g key={c.id}>
              {hoverChapter === c.id && (
                <rect x={colX(c.id) - colWidth / 2} y={MARGIN.top} width={colWidth} height={HEIGHT - MARGIN.top - MARGIN.bottom} fill="#b45309" opacity={0.06} />
              )}
              <text
                x={colX(c.id)}
                y={MARGIN.top - 8}
                textAnchor="middle"
                className="cursor-pointer select-none"
                style={{ fontSize: 10, fontFamily: "ui-monospace, monospace", fill: "rgba(0,0,0,0.5)" }}
                onMouseEnter={() => { setHoverChapter(c.id); setHovered({ kind: "chapter", id: c.id }); }}
                onMouseLeave={() => { setHoverChapter(null); setHovered(null); }}
                onClick={() => setSelected({ kind: "chapter", id: c.id })}
              >
                第{c.order_index}章
              </text>
            </g>
          ))}

          {/* 泳道行标签 + 结点连线 */}
          {threads.map((t, i) => {
            const y = threadRowY(i);
            const color = characterColor(t.id, i);
            const chapterIds = t.related_chapter_ids.filter((id) => orderById.has(id));
            const sorted = [...chapterIds].sort((a, b) => (orderById.get(a)! - orderById.get(b)!));
            const points: [number, number][] = sorted.map((id) => [colX(id), y]);
            const resolvedOrder = t.status === "resolved" && sorted.length ? orderById.get(sorted[sorted.length - 1])! : null;
            const isActive = sameRef(active, { kind: "thread", id: t.id });
            return (
              <g key={t.id} className="storymap-node" style={{ opacity: active && !isActive && active.kind === "thread" ? 0.3 : 1 }}>
                <line x1={MARGIN.left} y1={y} x2={WIDTH - MARGIN.right} y2={y} stroke={VIZ.grid} />
                <text
                  x={MARGIN.left - 8}
                  y={y + 3}
                  textAnchor="end"
                  className="cursor-pointer"
                  style={{ fontSize: 11, fill: isActive ? VIZ.ink : "rgba(0,0,0,0.65)", fontWeight: isActive ? 700 : 400 }}
                  onMouseEnter={() => setHovered({ kind: "thread", id: t.id })}
                  onMouseLeave={() => setHovered(null)}
                  onClick={() => setSelected({ kind: "thread", id: t.id })}
                >
                  {t.name.slice(0, 12)}
                </text>
                {points.length >= 2 && (
                  <path d={curve(points) || ""} fill="none" stroke={color} strokeWidth={2.5} opacity={t.status === "resolved" ? 0.5 : 0.9} />
                )}
                {/* resolved 线在回收章之后降透明：用一段淡色延伸线示意 */}
                {resolvedOrder != null && points.length > 0 && (
                  <line x1={points[points.length - 1][0]} y1={y} x2={colX(chapters[chapters.length - 1].id)} y2={y} stroke={color} strokeWidth={1} opacity={0.15} strokeDasharray="3 3" />
                )}
                {sorted.map((id) => (
                  <circle
                    key={id}
                    cx={colX(id)}
                    cy={y}
                    r={4}
                    fill={color}
                    stroke="#fff"
                    strokeWidth={1}
                    style={{ cursor: "pointer" }}
                    onMouseEnter={() => { setHoverChapter(id); setHovered({ kind: "thread", id: t.id }); }}
                    onMouseLeave={() => { setHoverChapter(null); setHovered(null); }}
                    onClick={() => setSelected({ kind: "thread", id: t.id })}
                  />
                ))}
              </g>
            );
          })}

          {/* 独立伏笔泳道 */}
          <line x1={MARGIN.left} y1={independentRowY} x2={WIDTH - MARGIN.right} y2={independentRowY} stroke={VIZ.grid} />
          <text x={MARGIN.left - 8} y={independentRowY + 3} textAnchor="end" style={{ fontSize: 11, fill: "rgba(0,0,0,0.5)" }}>
            独立伏笔
          </text>
          {data.foreshadowing.map((f) => {
            const anchorId = f.planted_chapter_id || f.resolved_chapter_id;
            if (!anchorId || !orderById.has(anchorId)) return null;
            const plantedOrder = f.planted_chapter_id ? orderById.get(f.planted_chapter_id) : undefined;
            const overdue = f.status !== "resolved" && plantedOrder != null && latestOrder - plantedOrder > 20;
            const color = foreshadowColor(f.status, overdue);
            const x = colX(anchorId);
            const isActive = sameRef(active, { kind: "foreshadow", id: f.id });
            return (
              <g
                key={f.id}
                transform={`translate(${x},${independentRowY})`}
                style={{ cursor: "pointer" }}
                onMouseEnter={() => setHovered({ kind: "foreshadow", id: f.id })}
                onMouseLeave={() => setHovered(null)}
                onClick={() => setSelected({ kind: "foreshadow", id: f.id })}
              >
                <rect x={-5} y={-5} width={10} height={10} transform="rotate(45)" fill={color} stroke="#fff" strokeWidth={isActive ? 2 : 1} />
                <title>{f.description}</title>
              </g>
            );
          })}
        </g>
      </svg>
      {threads.length === 0 && (
        <div className="border-t border-black/10 px-4 py-3 text-center text-xs text-black/40">
          还没有情节线。用 AI 提取或手动添加后，这里会织出章节 × 情节线的织线图。
        </div>
      )}
    </div>
  );
}
