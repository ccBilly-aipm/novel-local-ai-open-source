import bench from "../../data/checkerBench.json";

type Verdict = "pass" | "weak" | "fail" | "pending";

interface Row {
  label: string;
  service: string;
  paramB: number;
  category: string;
  r1: number | null;
  r2: number | null;
  r3: number | null;
  r4?: number | null;
  fa?: number;
  jsonOk: number;
  latencyS: number;
  thinking: number;
  verdict: Verdict;
  note: string;
}

// 错误轮（参与召回列）；clean 轮单独折算成「误报」。
const ERROR_ROUNDS = bench.rounds.filter((r) => r.key !== "clean");

const verdictMeta: Record<Verdict, { label: string; cls: string }> = {
  pass: { label: "✓ 可用", cls: "bg-green-100 text-green-700" },
  weak: { label: "△ 勉强", cls: "bg-amber-100 text-amber-800" },
  fail: { label: "✗ 不可用", cls: "bg-red-100 text-red-700" },
  pending: { label: "… 测试中", cls: "bg-black/5 text-black/45" },
};

// 召回/比率单元格配色：≥80 绿、≥40 琥珀、<40 红、null 灰横线。
function Cell({ v, suffix = "%" }: { v: number | null; suffix?: string }) {
  if (v === null || v === undefined) return <span className="text-black/25">—</span>;
  const cls = v >= 80 ? "text-green-700" : v >= 40 ? "text-amber-700" : "text-red-600";
  return <span className={`font-semibold ${cls}`}>{v}{suffix}</span>;
}

export default function CheckerBenchPanel() {
  const rows = bench.rows as Row[];
  return (
    <details className="panel overflow-hidden">
      <summary className="flex cursor-pointer list-none items-start justify-between gap-6 px-6 py-4">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-rust">Benchmark · Checker</div>
          <h2 className="mt-0.5 font-serif text-xl font-semibold">模型测试 · 连续性检查</h2>
          <p className="mt-1 text-xs text-black/45">
            哪些模型做了测试、用什么测、结果如何——实测而非连通性。更新于 {bench.generatedAt}。
          </p>
        </div>
        <span className="mt-1 shrink-0 rounded-full border border-black/10 px-3 py-1 text-xs text-black/45">点击展开</span>
      </summary>

      <div className="space-y-4 px-6 pb-6">
        {/* 测什么 + 参数 */}
        <div className="rounded-xl bg-black/[0.03] px-4 py-3 text-xs leading-5 text-black/65">
          <p><b>测试任务</b>：{bench.task}</p>
          <p className="mt-1"><b>统一参数</b>：{bench.options}</p>
          <p className="mt-1 text-black/45">{bench.materials}</p>
        </div>

        {/* 逐级递增的轮次说明 */}
        <div className="grid gap-2 sm:grid-cols-3">
          {bench.rounds.map((r) => (
            <div key={r.key} className="rounded-xl border border-black/10 bg-white/55 p-3">
              <div className="text-[11px] font-bold text-ink">{r.name}</div>
              <p className="mt-1 text-[10px] leading-4 text-black/50">{r.desc}</p>
            </div>
          ))}
        </div>

        {/* 结果表 */}
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="border-b border-black/15 text-left text-[10px] uppercase tracking-wide text-black/40">
                <th className="py-2 pr-3 font-semibold">模型</th>
                <th className="px-2 font-semibold">服务</th>
                {ERROR_ROUNDS.map((r, i) => (
                  <th key={r.key} className="px-2 text-center font-semibold">
                    R{i + 1}<br/>{r.name.replace(/^R\d+\s*/, "").split("·").pop()?.slice(0, 2)}
                  </th>
                ))}
                <th className="px-2 text-center font-semibold">误报</th>
                <th className="px-2 text-center font-semibold">JSON</th>
                <th className="px-2 text-center font-semibold">思考</th>
                <th className="px-2 text-center font-semibold">耗时</th>
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
                  <td className="px-2 py-2 whitespace-nowrap text-black/55">{row.service}</td>
                  {ERROR_ROUNDS.map((r) => (
                    <td key={r.key} className="px-2 py-2 text-center"><Cell v={(row as unknown as Record<string, number | null>)[r.key] ?? null} /></td>
                  ))}
                  <td className="px-2 py-2 text-center">
                    {row.fa == null ? <span className="text-black/25">—</span>
                      : <span className={`font-semibold ${row.fa === 0 ? "text-green-700" : row.fa <= 20 ? "text-amber-700" : "text-red-600"}`}>{row.fa}%</span>}
                  </td>
                  <td className="px-2 py-2 text-center"><Cell v={row.jsonOk} /></td>
                  <td className="px-2 py-2 text-center"><Cell v={row.thinking} /></td>
                  <td className="px-2 py-2 text-center whitespace-nowrap text-black/55">{row.latencyS}s</td>
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
          R1–R{ERROR_ROUNDS.length} 列为各难度「真矛盾召回率」（越高越能抓出矛盾、越不漏检）；「误报」列为合法章节被冤枉的比例（越低越好，0 为佳）。「思考」= 是否真触发推理。
        </p>

        {/* 排队中 */}
        {bench.queued?.length > 0 && (
          <div className="rounded-xl bg-amber-50/60 px-4 py-3 text-[11px] leading-5 text-amber-900/80">
            <b>排队待测（逐级补齐，同量级全测）</b>：{bench.queued.join("、")}
          </div>
        )}

        {/* 结论 */}
        <div className="rounded-xl border border-moss/30 bg-moss/[0.06] px-4 py-3 text-xs leading-5 text-ink">
          <b>结论</b>：{bench.conclusion}
        </div>
      </div>
    </details>
  );
}
