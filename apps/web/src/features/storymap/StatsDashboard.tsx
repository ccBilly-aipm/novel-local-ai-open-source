import { useMemo } from "react";
import type { StoryMap } from "../../types";
import { useSelection } from "./SelectionContext";
import { VIZ } from "./theme";

// V4 仪表盘：2×2 网格，D3 手绘 SVG。字数柱线图 / 连续性分数趋势 / 伏笔计数 / 人物×章节热力图。
export default function StatsDashboard({ data, onJumpCharacters }: { data: StoryMap; onJumpCharacters: () => void }) {
  return (
    <div className="grid grid-cols-2 gap-4">
      <Card title="各章字数（含移动平均）">
        <WordCountChart data={data} />
      </Card>
      <Card title="连续性分数趋势">
        <ScoreTrend data={data} />
      </Card>
      <Card title="伏笔状态">
        <ForeshadowCounts data={data} />
      </Card>
      <Card title="人物 × 章节 出场热力图">
        <PresenceHeatmap data={data} onJumpCharacters={onJumpCharacters} />
      </Card>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="panel p-4">
      <div className="label mb-2">{title}</div>
      {children}
    </div>
  );
}

const W = 400;
const H = 180;
const M = { top: 12, right: 12, bottom: 24, left: 32 };

function WordCountChart({ data }: { data: StoryMap }) {
  const chapters = data.chapters;
  if (chapters.length === 0) return <Empty />;
  const maxWc = Math.max(1, ...chapters.map((c) => c.word_count));
  const innerW = W - M.left - M.right;
  const innerH = H - M.top - M.bottom;
  const bw = innerW / chapters.length;
  // 移动平均（窗口 3）。
  const ma = chapters.map((_, i) => {
    const slice = chapters.slice(Math.max(0, i - 1), i + 2);
    return slice.reduce((s, c) => s + c.word_count, 0) / slice.length;
  });
  const maPts = ma.map((v, i) => `${M.left + i * bw + bw / 2},${M.top + innerH - (v / maxWc) * innerH}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {chapters.map((c, i) => {
        const h = (c.word_count / maxWc) * innerH;
        return (
          <rect key={c.id} x={M.left + i * bw + 1} y={M.top + innerH - h} width={Math.max(1, bw - 2)} height={h} fill={VIZ.resolved} opacity={0.55}>
            <title>第{c.order_index}章：{c.word_count} 字</title>
          </rect>
        );
      })}
      <polyline points={maPts} fill="none" stroke={VIZ.open} strokeWidth={1.5} />
      <line x1={M.left} y1={M.top + innerH} x2={W - M.right} y2={M.top + innerH} stroke={VIZ.grid} />
    </svg>
  );
}

function ScoreTrend({ data }: { data: StoryMap }) {
  const chapterOrder = new Map(data.chapters.map((c) => [c.id, c.order_index]));
  const points = data.stats.review_scores
    .map((s) => ({ order: chapterOrder.get(s.chapter_id) ?? 0, score: s.score }))
    .filter((p) => p.score != null)
    .sort((a, b) => a.order - b.order) as Array<{ order: number; score: number }>;
  if (points.length === 0) return <Empty text="暂无连续性分数（运行审稿后出现）" />;
  const innerW = W - M.left - M.right;
  const innerH = H - M.top - M.bottom;
  const maxOrder = Math.max(...points.map((p) => p.order), 1);
  const x = (o: number) => M.left + (maxOrder > 1 ? ((o - 1) / (maxOrder - 1)) * innerW : innerW / 2);
  const y = (s: number) => M.top + innerH - (s / 100) * innerH;
  // 空值断线：分段折线（此处已过滤 null，直接连有值点）。
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"} ${x(p.order)} ${y(p.score)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      <line x1={M.left} y1={M.top + innerH} x2={W - M.right} y2={M.top + innerH} stroke={VIZ.grid} />
      <path d={path} fill="none" stroke={VIZ.resolved} strokeWidth={2} />
      {points.map((p) => (
        <circle key={p.order} cx={x(p.order)} cy={y(p.score)} r={3} fill={VIZ.resolved}>
          <title>第{p.order}章：{p.score.toFixed(0)} 分</title>
        </circle>
      ))}
    </svg>
  );
}

function ForeshadowCounts({ data }: { data: StoryMap }) {
  const { open, resolved, overdue } = data.stats.foreshadow_counts;
  const total = open + resolved + overdue || 1;
  const stats = [
    { label: "开放", value: open, color: VIZ.open },
    { label: "已回收", value: resolved, color: VIZ.resolved },
    { label: "超期", value: overdue, color: VIZ.overdue },
  ];
  return (
    <div className="flex items-center gap-4 py-4">
      <svg viewBox="0 0 120 120" className="h-32 w-32 shrink-0">
        {(() => {
          let acc = 0;
          return stats.map((s) => {
            const frac = s.value / total;
            const start = acc * 2 * Math.PI - Math.PI / 2;
            acc += frac;
            const end = acc * 2 * Math.PI - Math.PI / 2;
            const large = end - start > Math.PI ? 1 : 0;
            const r = 50;
            const x1 = 60 + r * Math.cos(start);
            const y1 = 60 + r * Math.sin(start);
            const x2 = 60 + r * Math.cos(end);
            const y2 = 60 + r * Math.sin(end);
            if (s.value === 0) return null;
            return <path key={s.label} d={`M60,60 L${x1},${y1} A${r},${r} 0 ${large} 1 ${x2},${y2} Z`} fill={s.color} opacity={0.75} />;
          });
        })()}
        <circle cx={60} cy={60} r={28} fill="#f5f1e8" />
      </svg>
      <div className="space-y-2">
        {stats.map((s) => (
          <div key={s.label} className="flex items-center gap-2">
            <span className="inline-block h-3 w-3 rounded-full" style={{ background: s.color }} />
            <span className={`font-mono text-2xl font-semibold ${s.label === "超期" && s.value > 0 ? "text-viz-overdue" : ""}`}>{s.value}</span>
            <span className="text-xs text-black/45">{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function PresenceHeatmap({ data, onJumpCharacters }: { data: StoryMap; onJumpCharacters: () => void }) {
  const { setSelected } = useSelection();
  const chars = useMemo(
    () => [...data.characters].sort((a, b) => b.presence_chapters.length - a.presence_chapters.length).slice(0, 12),
    [data.characters],
  );
  const chapters = data.chapters;
  if (chars.length === 0 || chapters.length === 0) return <Empty />;
  const cellW = Math.min(24, (W - 90) / chapters.length);
  const cellH = 14;
  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${Math.max(W, 90 + chapters.length * cellW)} ${chars.length * (cellH + 2) + 24}`} style={{ minWidth: "100%" }}>
        {chars.map((c, ri) => {
          const presence = new Set(c.presence_chapters);
          return (
            <g key={c.id}>
              <text x={84} y={ri * (cellH + 2) + cellH} textAnchor="end" style={{ fontSize: 10, fill: "rgba(0,0,0,0.6)" }}>
                {c.name.slice(0, 6)}
              </text>
              {chapters.map((ch, ci) => {
                const on = presence.has(ch.order_index);
                return (
                  <rect
                    key={ch.id}
                    x={90 + ci * cellW}
                    y={ri * (cellH + 2)}
                    width={cellW - 1}
                    height={cellH}
                    fill={on ? VIZ.resolved : "rgba(0,0,0,0.05)"}
                    opacity={on ? 0.8 : 1}
                    style={{ cursor: on ? "pointer" : "default" }}
                    onClick={() => {
                      if (!on) return;
                      setSelected({ kind: "character", id: c.id });
                      onJumpCharacters();
                    }}
                  >
                    <title>{c.name} · 第{ch.order_index}章{on ? "（出场）" : ""}</title>
                  </rect>
                );
              })}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function Empty({ text = "暂无数据" }: { text?: string }) {
  return <div className="flex h-40 items-center justify-center text-xs text-black/35">{text}</div>;
}
