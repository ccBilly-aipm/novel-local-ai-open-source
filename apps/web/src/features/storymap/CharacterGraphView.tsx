import { useEffect, useMemo, useRef, useState } from "react";
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, Simulation } from "d3-force";
import type { StoryMap } from "../../types";
import { useSelection } from "./SelectionContext";
import { useZoom } from "./useZoom";
import { characterColor, RELATION_COLORS, sameRef, VIZ } from "./theme";

const WIDTH = 900;
const HEIGHT = 520;

interface Node {
  id: string;
  name: string;
  role: string;
  radius: number;
  isProtagonist: boolean;
  firstChapter: number;
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
}
interface Edge {
  source: string | Node;
  target: string | Node;
  type: string;
  minChapter: number;
}

// V2 人物关系网络：d3-force 力导向图；半径 ∝ 出场章数；主角六边形环；
// 边按关系类型着色；悬停一跳邻居高亮；底部章节滑块回放。
export default function CharacterGraphView({ data }: { data: StoryMap }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const gRef = useRef<SVGGElement>(null);
  const { hovered, selected, setHovered, setSelected } = useSelection();
  const [tick, setTick] = useState(0);
  const simRef = useRef<Simulation<Node, undefined> | null>(null);
  useZoom(svgRef, gRef, [0.3, 6], [data.characters.length]);

  const maxOrder = useMemo(
    () => (data.chapters.length ? Math.max(...data.chapters.map((c) => c.order_index)) : 1),
    [data.chapters],
  );
  const [sliderChapter, setSliderChapter] = useState<number>(maxOrder);
  useEffect(() => setSliderChapter(maxOrder), [maxOrder]);

  const charIndex = useMemo(() => new Map(data.characters.map((c, i) => [c.id, i])), [data.characters]);
  const maxPresence = useMemo(
    () => Math.max(1, ...data.characters.map((c) => c.presence_chapters.length)),
    [data.characters],
  );

  const nodes = useMemo<Node[]>(() => {
    return data.characters.map((c) => {
      const presence = c.presence_chapters.length;
      const isProt = c.role.includes("主角") || presence === maxPresence;
      return {
        id: c.id,
        name: c.name,
        role: c.role,
        radius: 12 + Math.sqrt(presence) * 6,
        isProtagonist: isProt,
        firstChapter: c.presence_chapters.length ? Math.min(...c.presence_chapters) : 0,
      };
    });
  }, [data.characters, maxPresence]);

  const edges = useMemo<Edge[]>(() => {
    const nodeIds = new Set(nodes.map((n) => n.id));
    return data.relationships
      .filter((r) => nodeIds.has(r.source_id) && nodeIds.has(r.target_id))
      .map((r) => {
        const s = data.characters.find((c) => c.id === r.source_id);
        const t = data.characters.find((c) => c.id === r.target_id);
        const sFirst = s && s.presence_chapters.length ? Math.min(...s.presence_chapters) : 0;
        const tFirst = t && t.presence_chapters.length ? Math.min(...t.presence_chapters) : 0;
        return { source: r.source_id, target: r.target_id, type: r.type, minChapter: Math.max(sFirst, tFirst) };
      });
  }, [data.relationships, data.characters, nodes]);

  // d3-force 仿真：tick 更新坐标 → setTick 触发 React 重渲染读 node.x/y。
  useEffect(() => {
    const sim = forceSimulation<Node>(nodes)
      .force("charge", forceManyBody().strength(-220))
      .force("center", forceCenter(WIDTH / 2, HEIGHT / 2))
      .force("collide", forceCollide<Node>().radius((d) => d.radius + 6))
      .force(
        "link",
        forceLink<Node, Edge>(edges)
          .id((d) => d.id)
          .distance((e) => (e.type === "family" ? 90 : 130))
          .strength(0.4),
      )
      .on("tick", () => setTick((t) => (t + 1) % 100000));
    simRef.current = sim;
    return () => {
      sim.stop();
    };
  }, [nodes, edges]);

  // 邻居索引（一跳高亮用）。
  const neighbors = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const e of edges) {
      const s = typeof e.source === "string" ? e.source : e.source.id;
      const t = typeof e.target === "string" ? e.target : e.target.id;
      map.set(s, (map.get(s) || new Set()).add(t));
      map.set(t, (map.get(t) || new Set()).add(s));
    }
    return map;
  }, [edges]);

  const active = hovered || selected;
  const activeCharId = active && active.kind === "character" ? active.id : null;

  function nodeVisible(n: Node): boolean {
    return n.firstChapter <= sliderChapter || n.firstChapter === 0;
  }
  function edgeVisible(e: Edge): boolean {
    return e.minChapter <= sliderChapter;
  }
  function dimmed(nodeId: string): boolean {
    if (!activeCharId) return false;
    if (nodeId === activeCharId) return false;
    return !(neighbors.get(activeCharId)?.has(nodeId));
  }

  void tick; // 触发重渲染读取仿真坐标

  const unmatchedCount = data.unmatched.length;

  return (
    <div className="panel overflow-hidden">
      <svg ref={svgRef} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full" style={{ height: HEIGHT, cursor: "grab" }}>
        <g ref={gRef}>
          {/* 边 */}
          {edges.filter(edgeVisible).map((e, i) => {
            const s = typeof e.source === "string" ? nodes.find((n) => n.id === e.source) : e.source;
            const t = typeof e.target === "string" ? nodes.find((n) => n.id === e.target) : e.target;
            if (!s || !t || s.x == null || t.x == null) return null;
            const sId = s.id;
            const tId = t.id;
            const faded = activeCharId ? !(sId === activeCharId || tId === activeCharId) : false;
            return (
              <line
                key={i}
                x1={s.x}
                y1={s.y}
                x2={t.x}
                y2={t.y}
                stroke={RELATION_COLORS[e.type] || RELATION_COLORS.other}
                strokeWidth={faded ? 1 : 2}
                opacity={faded ? 0.15 : 0.55}
                style={{ transition: "opacity 0.12s ease" }}
              />
            );
          })}
          {/* 节点 */}
          {nodes.filter(nodeVisible).map((n) => {
            if (n.x == null) return null;
            const color = characterColor(n.id, charIndex.get(n.id) ?? 0);
            const isDim = dimmed(n.id);
            const isActive = sameRef(active, { kind: "character", id: n.id });
            return (
              <g
                key={n.id}
                transform={`translate(${n.x},${n.y})`}
                className="storymap-node"
                style={{ cursor: "pointer", opacity: isDim ? 0.2 : 1 }}
                onMouseEnter={() => setHovered({ kind: "character", id: n.id })}
                onMouseLeave={() => setHovered(null)}
                onClick={() => setSelected({ kind: "character", id: n.id })}
              >
                {isActive && <circle r={n.radius + 5} fill={color} opacity={0.18} className="storymap-halo" />}
                {n.isProtagonist && <path d={hexPath(n.radius + 4)} fill="none" stroke={color} strokeWidth={1.5} />}
                <circle r={n.radius} fill={color} stroke="#fff" strokeWidth={1.5} />
                <text textAnchor="middle" dy={4} style={{ fontSize: Math.min(13, n.radius / 1.4), fill: "#fff", pointerEvents: "none", fontWeight: 600 }}>
                  {n.name.slice(0, 4)}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
      {/* 底部章节滑块（回放） + unmatched 提示 */}
      <div className="flex items-center gap-3 border-t border-black/10 px-4 py-2">
        <span className="text-xs text-black/50">回放到第 {sliderChapter} 章</span>
        <input
          type="range"
          min={1}
          max={maxOrder}
          value={sliderChapter}
          onChange={(e) => setSliderChapter(Number(e.target.value))}
          className="flex-1"
        />
        {unmatchedCount > 0 && (
          <span className="rounded-lg bg-amber-50 px-2 py-1 text-[11px] text-amber-800">
            {unmatchedCount} 条关系未匹配到人物
          </span>
        )}
      </div>
    </div>
  );
}

// 六边形描边环（E7）。
function hexPath(r: number): string {
  const pts = [];
  for (let i = 0; i < 6; i += 1) {
    const a = (Math.PI / 3) * i - Math.PI / 2;
    pts.push(`${(Math.cos(a) * r).toFixed(1)},${(Math.sin(a) * r).toFixed(1)}`);
  }
  return "M" + pts.join("L") + "Z";
}
