// 空状态引导卡：没有任何 timeline/thread/伏笔/关系数据时显示（不显示空白坐标系）。
export default function EmptyState({ onExtract }: { onExtract: () => void }) {
  return (
    <div className="panel flex min-h-[560px] flex-col items-center justify-center p-10 text-center">
      <div className="mb-4 text-5xl">🗺️</div>
      <h3 className="font-serif text-2xl font-semibold">还没有故事结构可以画</h3>
      <p className="mt-3 max-w-md text-sm leading-6 text-black/50">
        用 AI 从已提交的章节里提取时间线事件、人物关系、情节线与伏笔，或手动添加，
        故事地图就会把它们画成可缩放、可联动的四视图。
      </p>
      <div className="mt-6 flex items-center gap-3">
        <button className="btn-primary" onClick={onExtract}>
          🔍 用 AI 从章节提取故事结构
        </button>
      </div>
      <p className="mt-4 text-xs text-black/40">
        也可以用右上角「＋手动添加」逐条录入。提取需要至少一个可用的模型 Provider。
      </p>
    </div>
  );
}
