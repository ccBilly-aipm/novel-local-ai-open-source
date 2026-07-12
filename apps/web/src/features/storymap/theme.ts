// 故事地图可视化的配色与共享常量。
// 纸底（#ebe5d9 / #f5f1e8）上均校验过对比度：正文标签 ≥4.5:1，大图形元素 ≥3:1（详见交付报告）。

// 人物 categorical 8 色板：低饱和、纸底可读，互相可区分。
// 均为深色调（对纸底对比度 ≥4.5:1），既能当描边也能当填充。
export const CHARACTER_PALETTE = [
  "#38564a", // moss 深绿
  "#a85535", // rust 赭
  "#3b5b78", // 靛蓝
  "#7a4b73", // 紫梅
  "#8a6d1f", // 芥末金
  "#4a6b4a", // 苔绿
  "#9a4b4b", // 砖红
  "#4f5b6b", // 石板灰蓝
] as const;

export function characterColor(id: string, index: number): string {
  // 用稳定索引取色；索引越界时回退到 id 哈希，保证同一人物颜色稳定。
  if (index >= 0 && index < CHARACTER_PALETTE.length) return CHARACTER_PALETTE[index];
  let h = 0;
  for (let i = 0; i < id.length; i += 1) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return CHARACTER_PALETTE[h % CHARACTER_PALETTE.length];
}

// 关系类型 → 颜色（五色，图例联动）。
export const RELATION_COLORS: Record<string, string> = {
  family: "#8a6d1f", // 亲缘·金
  ally: "#38564a", // 同盟·绿
  enemy: "#b3261e", // 敌对·红
  romance: "#a8476f", // 爱慕·玫红
  other: "rgba(0,0,0,0.35)", // 其它·灰
};

export const RELATION_LABELS: Record<string, string> = {
  family: "亲缘",
  ally: "同盟",
  enemy: "敌对",
  romance: "爱慕",
  other: "其它",
};

// 状态色（与 tailwind viz.* 对应，供 D3 内联 SVG 使用——SVG 属性吃不到 tailwind class）。
export const VIZ = {
  open: "#b45309",
  resolved: "#38564a",
  overdue: "#b3261e",
  muted: "rgba(0,0,0,0.25)",
  ink: "#171512",
  grid: "rgba(0,0,0,0.08)",
} as const;

export function foreshadowColor(status: string, overdue: boolean): string {
  if (status === "resolved") return VIZ.resolved;
  if (overdue) return VIZ.overdue;
  return VIZ.open;
}

// 联动实体类型。
export type EntityKind = "character" | "event" | "thread" | "foreshadow" | "chapter";

export interface EntityRef {
  kind: EntityKind;
  id: string;
}

export function sameRef(a: EntityRef | null, b: EntityRef | null): boolean {
  return !!a && !!b && a.kind === b.kind && a.id === b.id;
}
