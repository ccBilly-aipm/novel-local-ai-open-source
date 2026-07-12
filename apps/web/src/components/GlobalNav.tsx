export type GlobalPage = "projects" | "runs" | "models" | "prompts" | "settings";

interface Props {
  active: GlobalPage;
  waitingCount: number;
  onNavigate: (page: GlobalPage) => void;
}

// 本地模型 / 提示词 已并入「设置」页（子标签），顶部导航精简为三项。
const items: Array<[GlobalPage, string]> = [
  ["projects", "项目"],
  ["runs", "运行记录"],
  ["settings", "设置"],
];

export default function GlobalNav({ active, waitingCount, onNavigate }: Props) {
  return (
    <header className="sticky top-0 z-40 flex h-16 items-center border-b border-white/10 bg-[#11171b] px-6 text-white shadow-sm">
      <button className="mr-10 text-left" onClick={() => onNavigate("projects")}>
        <div className="text-[9px] uppercase tracking-[0.24em] text-white/35">Local-first studio</div>
        <div className="font-serif text-lg font-semibold">Novel Local AI</div>
      </button>
      <nav className="flex h-full items-center gap-1">
        {items.map(([key, label]) => (
          <button
            key={key}
            className={`relative h-full px-4 text-sm font-semibold transition ${
              active === key ? "text-white" : "text-white/50 hover:text-white"
            }`}
            onClick={() => onNavigate(key)}
          >
            {label}
            {key === "runs" && waitingCount > 0 && (
              <span className="ml-2 rounded-full bg-rust px-2 py-0.5 text-[10px] text-white">{waitingCount}</span>
            )}
            {active === key && <span className="absolute inset-x-3 bottom-0 h-0.5 bg-[#d79b78]" />}
          </button>
        ))}
      </nav>
      <div className="ml-auto rounded-full border border-white/10 px-3 py-1.5 text-[10px] text-white/40">
        本地数据 · SQLite
      </div>
    </header>
  );
}
