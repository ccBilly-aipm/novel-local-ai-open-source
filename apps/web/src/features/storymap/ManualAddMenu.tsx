import { useState } from "react";
import type { StoryMapChapter } from "../../types";
import EntityForm, { EntityFormKind } from "./EntityForm";

// 「＋手动添加」下拉：事件 / 情节线 / 伏笔，各打开同款表单（POST 新建）。
export default function ManualAddMenu({
  novelId,
  chapters,
  onDone,
}: {
  novelId: string;
  chapters: StoryMapChapter[];
  onDone: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [formKind, setFormKind] = useState<EntityFormKind | null>(null);

  return (
    <div className="relative">
      <button className="btn-soft" onClick={() => setOpen((v) => !v)}>
        ＋ 手动添加
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 w-40 overflow-hidden rounded-xl border border-black/10 bg-white shadow-panel">
          {(
            [
              ["event", "时间线事件"],
              ["thread", "情节线"],
              ["foreshadow", "伏笔"],
            ] as Array<[EntityFormKind, string]>
          ).map(([kind, label]) => (
            <button
              key={kind}
              className="block w-full px-4 py-2 text-left text-sm hover:bg-black/5"
              onClick={() => {
                setFormKind(kind);
                setOpen(false);
              }}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {formKind && (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/30 p-4" onClick={() => setFormKind(null)}>
          <div className="panel w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
            <EntityForm
              kind={formKind}
              novelId={novelId}
              chapters={chapters}
              onDone={() => {
                setFormKind(null);
                onDone();
              }}
              onCancel={() => setFormKind(null)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
