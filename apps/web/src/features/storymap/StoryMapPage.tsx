import { useState } from "react";
import type { ModelProvider, Novel } from "../../types";
import { SelectionProvider } from "./SelectionContext";
import { useStoryMapData } from "./useStoryMapData";
import TimelineView from "./TimelineView";
import CharacterGraphView from "./CharacterGraphView";
import ThreadWeaveView from "./ThreadWeaveView";
import StatsDashboard from "./StatsDashboard";
import DetailPanel from "./DetailPanel";
import ExtractDialog from "./ExtractDialog";
import ManualAddMenu from "./ManualAddMenu";
import Legend from "./Legend";
import EmptyState from "./EmptyState";

interface Props {
  projectId: string;
  novel: Novel;
  providers: ModelProvider[];
}

type ViewTab = "timeline" | "characters" | "threads" | "dashboard";

const VIEW_TABS: Array<[ViewTab, string]> = [
  ["timeline", "时间线"],
  ["characters", "人物网络"],
  ["threads", "故事线"],
  ["dashboard", "仪表盘"],
];

export default function StoryMapPage({ projectId, novel, providers }: Props) {
  const { data, loading, error, refetch } = useStoryMapData(novel.id);
  const [tab, setTab] = useState<ViewTab>("timeline");
  const [extractOpen, setExtractOpen] = useState(false);

  const isEmpty =
    !!data &&
    data.timeline_events.length === 0 &&
    data.plot_threads.length === 0 &&
    data.foreshadowing.length === 0 &&
    data.relationships.length === 0;

  return (
    <SelectionProvider>
      <div className="p-6">
        {/* 视图 tab 行 + 动作区 */}
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-1 rounded-xl border border-black/10 bg-white/60 p-1">
            {VIEW_TABS.map(([key, label]) => (
              <button
                key={key}
                className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${
                  tab === key ? "bg-ink text-white shadow-sm" : "text-black/50 hover:text-black"
                }`}
                onClick={() => setTab(key)}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <button className="btn-primary" onClick={() => setExtractOpen(true)}>
              🔍 AI 提取
            </button>
            <ManualAddMenu novelId={novel.id} chapters={data?.chapters || []} onDone={refetch} />
          </div>
        </div>

        {loading && !data ? (
          <div className="panel p-10 text-center text-sm text-black/45">正在加载故事地图…</div>
        ) : error ? (
          <div className="panel p-10 text-center">
            <p className="text-sm text-rust">{error}</p>
            <button className="btn-soft mt-4" onClick={() => void refetch()}>
              重试
            </button>
          </div>
        ) : data ? (
          <div className="flex gap-4">
            {/* 主画布区 */}
            <div className="min-h-[560px] flex-1">
              {isEmpty ? (
                <EmptyState onExtract={() => setExtractOpen(true)} />
              ) : tab === "timeline" ? (
                <TimelineView data={data} />
              ) : tab === "characters" ? (
                <CharacterGraphView data={data} />
              ) : tab === "threads" ? (
                <ThreadWeaveView data={data} />
              ) : (
                <StatsDashboard data={data} onJumpCharacters={() => setTab("characters")} />
              )}
            </div>
            {/* 常驻右侧详情面板 */}
            <div className="w-[320px] shrink-0">
              <DetailPanel
                data={data}
                projectId={projectId}
                view={tab}
                onChanged={refetch}
                onJump={(view) => setTab(view)}
              />
            </div>
          </div>
        ) : null}

        {data && !isEmpty && <Legend data={data} />}

        {extractOpen && (
          <ExtractDialog
            novelId={novel.id}
            providers={providers}
            chapters={data?.chapters || []}
            onClose={() => setExtractOpen(false)}
            onAccepted={refetch}
          />
        )}
      </div>
    </SelectionProvider>
  );
}

export type { ViewTab };
