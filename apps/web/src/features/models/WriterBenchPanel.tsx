import bench from "../../data/writerBench.json";

type Verdict = "best" | "good" | "weak" | "fail";

interface Q { prose: number; coherence: number; tension: number; voice: number; restraint: number; }
interface Row {
  label: string;
  service: string;
  paramB: number;
  category: string;
  overall: number | null;
  wc: number | null;
  genS: number | null;
  beats: number | null;
  canonClean: boolean | null;
  formatOk: boolean | null;
  len: string;
  q: Q | null;
  verdict: Verdict;
  note: string;
}

const verdictMeta: Record<Verdict, { label: string; cls: string }> = {
  best: { label: "✓ 推荐", cls: "bg-green-100 text-green-700" },
  good: { label: "○ 可用", cls: "bg-sky-100 text-sky-700" },
  weak: { label: "△ 勉强", cls: "bg-amber-100 text-amber-800" },
  fail: { label: "✗ 不可用", cls: "bg-red-100 text-red-700" },
};

const QDIMS: { key: keyof Q; name: string }[] = [
  { key: "prose", name: "文笔" }, { key: "coherence", name: "连贯" }, { key: "tension", name: "张力" },
  { key: "voice", name: "声音" }, { key: "restraint", name: "节制" },
];

function score(v: number | null) {
  if (v == null) return <span className="text-black/25">—</span>;
  const cls = v >= 4.5 ? "text-green-700" : v >= 3.5 ? "text-sky-700" : v >= 2.5 ? "text-amber-700" : "text-red-600";
  return <span className={`font-semibold ${cls}`}>{v}</span>;
}

export default function WriterBenchPanel() {
  const rows = bench.rows as Row[];
  return (
    <details className="panel overflow-hidden">
      <summary className="flex cursor-pointer list-none items-start justify-between gap-6 px-6 py-4">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-rust">Benchmark · Writer</div>
          <h2 className="mt-0.5 font-serif text-xl font-semibold">模型测试 · 正文写作</h2>
          <p className="mt-1 text-xs text-black/45">
            同一章节、同款提示词，比指令遵循 + 文笔(LLM 评委打分)。更新于 {bench.generatedAt}。
          </p>
        </div>
        <span className="mt-1 shrink-0 rounded-full border border-black/10 px-3 py-1 text-xs text-black/45">点击展开</span>
      </summary>

      <div className="space-y-4 px-6 pb-6">
        <div className="rounded-xl bg-black/[0.03] px-4 py-3 text-xs leading-5 text-black/65">
          <p><b>测试任务</b>：{bench.task}</p>
          <p className="mt-1"><b>评分</b>：{bench.dims}</p>
          <p className="mt-1 text-black/45">{bench.method}</p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="border-b border-black/15 text-left text-[10px] uppercase tracking-wide text-black/40">
                <th className="py-2 pr-3 font-semibold">模型</th>
                <th className="px-2 text-center font-semibold">综合</th>
                <th className="px-2 text-center font-semibold">字数</th>
                <th className="px-2 text-center font-semibold">耗时</th>
                <th className="px-2 text-center font-semibold">节点</th>
                <th className="px-2 text-center font-semibold">canon</th>
                {QDIMS.map((d) => <th key={d.key} className="px-1.5 text-center font-semibold">{d.name}</th>)}
                <th className="px-2 text-center font-semibold">结论</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.label} className="border-b border-black/5 align-top">
                  <td className="py-2 pr-3">
                    <div className="font-semibold text-ink">{row.label}</div>
                    <div className="mt-0.5 text-[10px] leading-4 text-black/45">{row.note}</div>
                  </td>
                  <td className="px-2 py-2 text-center">
                    {row.overall == null ? <span className="text-black/25">—</span>
                      : <span className={`font-bold ${row.overall >= 7.5 ? "text-green-700" : row.overall >= 6 ? "text-amber-700" : "text-red-600"}`}>{row.overall}</span>}
                  </td>
                  <td className="px-2 py-2 text-center whitespace-nowrap text-black/55">
                    {row.wc == null ? "—" : <span className={row.len === "合适" ? "text-green-700" : row.len.includes("超长") ? "text-red-600" : "text-amber-700"}>{row.wc}</span>}
                  </td>
                  <td className="px-2 py-2 text-center whitespace-nowrap text-black/55">{row.genS == null ? "—" : `${row.genS}s`}</td>
                  <td className="px-2 py-2 text-center text-black/55">{row.beats == null ? "—" : `${row.beats}/6`}</td>
                  <td className="px-2 py-2 text-center">
                    {row.canonClean == null ? <span className="text-black/25">—</span>
                      : row.canonClean ? <span className="text-green-700">✓净</span> : <span className="text-red-600">✗违规</span>}
                  </td>
                  {QDIMS.map((d) => <td key={d.key} className="px-1.5 py-2 text-center">{score(row.q ? row.q[d.key] : null)}</td>)}
                  <td className="px-2 py-2 text-center">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${verdictMeta[row.verdict].cls}`}>
                      {verdictMeta[row.verdict].label}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-[10px] leading-4 text-black/40">
          综合 = 3 评委均分(1–10)；字数绿=达标(800–1600)、红=超长；canon=是否踩不可变规则/角色卡；文笔五维各 1–5。
        </p>

        <div className="rounded-xl border border-moss/30 bg-moss/[0.06] px-4 py-3 text-xs leading-5 text-ink">
          <b>结论</b>：{bench.conclusion}
        </div>
      </div>
    </details>
  );
}
