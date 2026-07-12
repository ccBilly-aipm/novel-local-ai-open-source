import { useEffect, useRef, useState } from "react";
import { api, parseJson } from "../../services/api";
import type { ModelProvider, StagedCandidate, StoryMapChapter, StoryMapExtractRun } from "../../types";

interface Props {
  novelId: string;
  providers: ModelProvider[];
  chapters: StoryMapChapter[];
  onClose: () => void;
  onAccepted: () => void;
}

const STORYMAP_TYPES = [
  "staged_storymap_event",
  "staged_storymap_relationship",
  "staged_storymap_thread",
  "staged_storymap_foreshadow",
];
const TYPE_LABEL: Record<string, string> = {
  staged_storymap_event: "时间线事件",
  staged_storymap_relationship: "人物关系",
  staged_storymap_thread: "情节线",
  staged_storymap_foreshadow: "伏笔",
};

type Phase = "config" | "running" | "review";

export default function ExtractDialog({ novelId, providers, chapters, onClose, onAccepted }: Props) {
  const [phase, setPhase] = useState<Phase>("config");
  const [providerId, setProviderId] = useState(providers.find((p) => p.enabled)?.id || providers[0]?.id || "");
  const [scope, setScope] = useState<"all" | "custom">("all");
  const [selectedChapters, setSelectedChapters] = useState<Set<string>>(new Set());
  const [run, setRun] = useState<StoryMapExtractRun | null>(null);
  const [candidates, setCandidates] = useState<StagedCandidate[]>([]);
  const [message, setMessage] = useState("");
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, []);

  async function loadCandidates() {
    const rows = await api<StagedCandidate[]>(`/novels/${novelId}/story-engineering/candidates?status=staged`);
    setCandidates(rows.filter((r) => STORYMAP_TYPES.includes(r.record_type)));
  }

  async function start() {
    if (!providerId) {
      setMessage("请先选择一个模型 Provider");
      return;
    }
    try {
      const body: Record<string, unknown> = { provider_id: providerId };
      if (scope === "custom") body.chapter_ids = Array.from(selectedChapters);
      const started = await api<StoryMapExtractRun>(`/novels/${novelId}/story-map/extract`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setRun(started);
      setPhase("running");
      // 轮询进度（沿用现有约 2s 节奏）。
      pollRef.current = window.setInterval(async () => {
        try {
          const fresh = await api<StoryMapExtractRun>(`/novels/${novelId}/story-map/extract-runs/${started.id}`);
          setRun(fresh);
          if (fresh.status === "completed" || fresh.status === "failed") {
            if (pollRef.current) window.clearInterval(pollRef.current);
            await loadCandidates();
            setPhase("review");
          }
        } catch {
          /* 轮询失败下次再试 */
        }
      }, 2000);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "启动提取失败");
    }
  }

  async function act(candidateId: string, action: "accept" | "reject") {
    await api(`/story-engineering/candidates/${candidateId}/${action}`, { method: "POST" });
    setCandidates((cs) => cs.filter((c) => c.id !== candidateId));
    onAccepted();
  }

  async function acceptAllHighConfidence() {
    const high = candidates.filter((c) => confidenceOf(c) >= 0.7);
    for (const c of high) {
      try {
        await api(`/story-engineering/candidates/${c.id}/accept`, { method: "POST" });
      } catch {
        /* 单条失败不阻断其余 */
      }
    }
    await loadCandidates();
    onAccepted();
  }

  const grouped = STORYMAP_TYPES.map((t) => ({ type: t, items: candidates.filter((c) => c.record_type === t) }));
  const progressPct = run && run.total_chapters > 0 ? Math.round((run.processed_chapters / run.total_chapters) * 100) : 0;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="panel flex max-h-[85vh] w-full max-w-2xl flex-col p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="font-serif text-2xl font-semibold">AI 提取故事结构</h3>
          <button className="text-black/40 hover:text-black" onClick={onClose}>
            ✕
          </button>
        </div>

        {phase === "config" && (
          <div className="space-y-4">
            <div>
              <label className="label">模型 Provider</label>
              <select className="field" value={providerId} onChange={(e) => setProviderId(e.target.value)}>
                {providers.length === 0 && <option value="">（无可用 Provider，请先在设置里配置）</option>}
                {providers.map((p) => (
                  <option key={p.id} value={p.id} disabled={!p.enabled}>
                    {p.name} {p.enabled ? "" : "（已禁用）"}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">提取范围</label>
              <div className="flex gap-2">
                <button className={`btn-soft flex-1 ${scope === "all" ? "border-moss bg-white" : ""}`} onClick={() => setScope("all")}>
                  全部有正文的章节
                </button>
                <button className={`btn-soft flex-1 ${scope === "custom" ? "border-moss bg-white" : ""}`} onClick={() => setScope("custom")}>
                  自选章节
                </button>
              </div>
            </div>
            {scope === "custom" && (
              <div className="max-h-48 overflow-y-auto rounded-xl border border-black/10 p-2">
                {chapters.map((c) => (
                  <label key={c.id} className="flex items-center gap-2 px-2 py-1 text-sm">
                    <input
                      type="checkbox"
                      checked={selectedChapters.has(c.id)}
                      onChange={(e) => {
                        setSelectedChapters((s) => {
                          const next = new Set(s);
                          if (e.target.checked) next.add(c.id);
                          else next.delete(c.id);
                          return next;
                        });
                      }}
                    />
                    第{c.order_index}章 · {c.title}
                  </label>
                ))}
                {chapters.length === 0 && <p className="p-2 text-xs text-black/40">暂无章节。</p>}
              </div>
            )}
            {message && <p className="text-xs text-rust">{message}</p>}
            <div className="flex justify-end gap-2">
              <button className="btn-soft" onClick={onClose}>
                取消
              </button>
              <button className="btn-primary" onClick={() => void start()}>
                开始提取
              </button>
            </div>
          </div>
        )}

        {phase === "running" && run && (
          <div className="py-8 text-center">
            <div className="mx-auto mb-4 h-2 w-full max-w-sm overflow-hidden rounded-full bg-black/10">
              <div className="h-full bg-moss transition-all" style={{ width: `${progressPct}%` }} />
            </div>
            <p className="text-sm text-black/60">
              正在提取 {run.processed_chapters} / {run.total_chapters} 章
            </p>
            {run.current_chapter_title && <p className="mt-1 text-xs text-black/40">当前：{run.current_chapter_title}</p>}
          </div>
        )}

        {phase === "review" && (
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-sm text-black/60">
                提取完成，共 {candidates.length} 条候选
                {run?.error_code === "PARTIAL" && <span className="ml-2 text-amber-700">（部分章节失败）</span>}
              </p>
              {candidates.length > 0 && (
                <button className="btn-soft" onClick={() => void acceptAllHighConfidence()}>
                  全部接受高置信 (≥0.7)
                </button>
              )}
            </div>
            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
              {candidates.length === 0 && (
                <p className="py-8 text-center text-sm text-black/40">没有可处理的候选。{run?.error_code === "PARTIAL" ? "部分章节提取失败，可重试。" : ""}</p>
              )}
              {grouped.map(({ type, items }) =>
                items.length === 0 ? null : (
                  <div key={type}>
                    <div className="label">{TYPE_LABEL[type]}（{items.length}）</div>
                    <div className="space-y-2">
                      {items.map((c) => (
                        <CandidateRow key={c.id} candidate={c} onAccept={() => void act(c.id, "accept")} onReject={() => void act(c.id, "reject")} />
                      ))}
                    </div>
                  </div>
                ),
              )}
            </div>
            <div className="mt-3 flex justify-end border-t border-black/10 pt-3">
              <button className="btn-primary" onClick={onClose}>
                完成
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function confidenceOf(c: StagedCandidate): number {
  const payload = parseJson<Record<string, unknown>>(c.content_json, {});
  const v = payload.confidence;
  return typeof v === "number" ? v : 0.6;
}

function CandidateRow({ candidate, onAccept, onReject }: { candidate: StagedCandidate; onAccept: () => void; onReject: () => void }) {
  const payload = parseJson<Record<string, unknown>>(candidate.content_json, {});
  const conf = confidenceOf(candidate);
  const title =
    String(payload.title || payload.name || payload.description || payload.source_name || "候选").slice(0, 60) +
    (payload.target_name ? ` → ${payload.target_name}` : "");
  const evidence = String(payload.evidence || "");
  return (
    <div className="rounded-xl border border-black/10 bg-white/60 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">{title}</div>
          {evidence && <div className="mt-1 truncate text-xs text-black/40">证据：{evidence}</div>}
        </div>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${conf >= 0.7 ? "bg-green-100 text-green-700" : "bg-black/5 text-black/45"}`}>
          {(conf * 100).toFixed(0)}%
        </span>
      </div>
      <div className="mt-2 flex gap-2">
        <button className="btn-soft flex-1 py-1 text-xs" onClick={onAccept}>
          接受
        </button>
        <button className="btn-soft flex-1 py-1 text-xs text-black/50" onClick={onReject}>
          忽略
        </button>
      </div>
    </div>
  );
}
