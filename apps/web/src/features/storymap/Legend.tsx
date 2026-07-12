import type { StoryMap } from "../../types";
import { RELATION_COLORS, RELATION_LABELS, VIZ } from "./theme";

// 底部图例行：状态色 · 关系色板 · 交互提示。unmatched 关系在此提示。
export default function Legend({ data }: { data: StoryMap }) {
  return (
    <div className="panel mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 text-xs text-black/55">
      <div className="flex items-center gap-2">
        <span className="font-semibold text-black/70">状态</span>
        <Swatch color={VIZ.open} label="进行中/开放" />
        <Swatch color={VIZ.resolved} label="已回收/收束" />
        <Swatch color={VIZ.overdue} label="超期" />
      </div>
      <div className="flex items-center gap-2">
        <span className="font-semibold text-black/70">关系</span>
        {Object.entries(RELATION_LABELS).map(([key, label]) => (
          <Swatch key={key} color={RELATION_COLORS[key]} label={label} />
        ))}
      </div>
      <div className="text-black/40">滚轮缩放 · 拖拽平移 · 双击复位</div>
      {data.unmatched.length > 0 && (
        <div className="rounded-lg bg-amber-50 px-2 py-1 text-amber-800">
          {data.unmatched.length} 条关系未匹配到人物，可在详情面板处理
        </div>
      )}
    </div>
  );
}

function Swatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="inline-block h-3 w-3 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}
