import type { Chapter, Character, ContextPreview, WorldRule } from "../../types";

interface Props {
  chapter: Chapter;
  characters: Character[];
  rules: WorldRule[];
  context: ContextPreview | null;
}

export default function ContextInspector({ chapter, characters, rules, context }: Props) {
  const characterIds = (() => {
    try {
      return JSON.parse(chapter.outline?.character_ids_json || "[]") as string[];
    } catch {
      return [];
    }
  })();
  const related = characters.filter((character) => characterIds.includes(character.id));

  return (
    <div className="space-y-4">
      <section className="panel p-4">
        <div className="label">本章目标</div>
        <p className="text-sm leading-6 text-black/65">{chapter.outline?.goal || "尚未填写目标"}</p>
        <div className="label mt-4">章节大纲</div>
        <p className="max-h-36 overflow-y-auto whitespace-pre-wrap text-xs leading-5 text-black/55">
          {chapter.outline?.outline_content || "尚未填写章节大纲"}
        </p>
      </section>
      <section className="panel p-4">
        <div className="label">相关人物</div>
        <div className="flex flex-wrap gap-2">
          {related.map((character) => <span key={character.id} className="rounded-full bg-moss/10 px-2 py-1 text-xs text-moss">{character.name}</span>)}
          {related.length === 0 && <span className="text-xs text-black/40">尚未关联角色</span>}
        </div>
        <div className="label mt-4">高优先级世界规则</div>
        <div className="space-y-2 text-xs text-black/55">
          {[...rules].sort((a, b) => b.priority - a.priority).slice(0, 4).map((rule) => (
            <div key={rule.id}><b>{rule.name}</b><span className="ml-2 text-black/35">P{rule.priority}</span></div>
          ))}
          {rules.length === 0 && <span className="text-black/40">尚无世界规则</span>}
        </div>
      </section>
      <details className="panel p-4">
        <summary className="cursor-pointer font-semibold">上下文预览</summary>
        {context ? (
          <div className="mt-3">
            <div className="mb-2 text-xs text-black/40">估算 {context.estimated_tokens} / {context.budget} tokens</div>
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-xl bg-ink p-3 text-[10px] leading-5 text-white/70">{context.rendered_context}</pre>
          </div>
        ) : <p className="mt-3 text-xs text-black/40">选择章节后加载。</p>}
      </details>
    </div>
  );
}
