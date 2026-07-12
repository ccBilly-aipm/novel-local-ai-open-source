import type { ChapterVersion } from "../../types";

interface Props {
  version: ChapterVersion | null;
  versions: ChapterVersion[];
  onSelect: (version: ChapterVersion) => void;
  onRestore?: (version: ChapterVersion) => void;
  approvedVersionId: string | null;
  autoCommitEnabled?: boolean;
  className?: string;
}

export default function VersionPreview({
  version,
  versions,
  onSelect,
  onRestore,
  approvedVersionId,
  autoCommitEnabled = false,
  className = "",
}: Props) {
  if (!version) {
    return <section className={`panel ${className}`} aria-label="暂无章节版本" />;
  }
  return (
    <section className={`panel flex min-h-0 flex-col overflow-hidden ${className}`}>
      <header className="flex shrink-0 items-center justify-between border-b border-black/10 px-5 py-4">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-rust">Immutable chapter version</div>
          <h2 className="mt-1 font-serif text-xl font-semibold">AI 版本 v{version.version_number}</h2>
        </div>
        <div className="flex items-center gap-2">
          <select
            className="field w-auto min-w-40"
            value={version.id}
            onChange={(event) => {
              const selected = versions.find((item) => item.id === event.target.value);
              if (selected) onSelect(selected);
            }}
          >
            {versions.map((item) => (
              <option key={item.id} value={item.id}>
                v{item.version_number} · {item.kind}{approvedVersionId === item.id ? " · 已批准" : ""}
              </option>
            ))}
          </select>
          {onRestore && <button className="btn-soft whitespace-nowrap" onClick={() => onRestore(version)}>恢复为正文</button>}
        </div>
      </header>
      <div className="shrink-0 border-b border-amber-200 bg-amber-50 px-5 py-3 text-xs text-amber-900">
        {autoCommitEnabled
          ? "此内容是不可变候选版本。AI 会依据连续性报告修订、复检，通过安全阈值后才写入 Chapter.content。"
          : "此内容是不可变候选版本。只有点击“批准并写入正文”后，才会更新 Chapter.content。"}
      </div>
      <article className="min-h-0 flex-1 overflow-y-auto whitespace-pre-wrap px-7 py-6 font-serif text-base leading-8">
        {version.content_markdown}
      </article>
    </section>
  );
}
