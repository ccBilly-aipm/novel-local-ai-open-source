import { createContext, ReactNode, useContext, useMemo, useState } from "react";
import type { EntityRef } from "./theme";

// 全局联动状态：任何视图 hover/click 都写它，所有视图订阅并高亮自己画布内的关联元素。
// 切换 tab 保留 selected（hovered 是瞬时的，切 tab 自然清空）。
interface SelectionState {
  hovered: EntityRef | null;
  selected: EntityRef | null;
  setHovered: (ref: EntityRef | null) => void;
  setSelected: (ref: EntityRef | null) => void;
}

const SelectionCtx = createContext<SelectionState | null>(null);

export function SelectionProvider({ children }: { children: ReactNode }) {
  const [hovered, setHovered] = useState<EntityRef | null>(null);
  const [selected, setSelected] = useState<EntityRef | null>(null);
  const value = useMemo(
    () => ({ hovered, selected, setHovered, setSelected }),
    [hovered, selected],
  );
  return <SelectionCtx.Provider value={value}>{children}</SelectionCtx.Provider>;
}

export function useSelection(): SelectionState {
  const ctx = useContext(SelectionCtx);
  if (!ctx) throw new Error("useSelection must be used within SelectionProvider");
  return ctx;
}
