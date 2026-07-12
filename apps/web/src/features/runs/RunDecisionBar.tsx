import { useState } from "react";

interface Props {
  disabled: boolean;
  busy: boolean;
  onApprove: (feedback: string) => Promise<void>;
  onReject: (feedback: string) => Promise<void>;
  onRevise: (feedback: string) => Promise<void>;
}

export default function RunDecisionBar({ disabled, busy, onApprove, onReject, onRevise }: Props) {
  const [mode, setMode] = useState<"reject" | "revise" | null>(null);
  const [feedback, setFeedback] = useState("");

  async function approve() {
    if (!window.confirm("批准后会用当前 AI 版本更新正式章节正文。确认继续？")) return;
    await onApprove("人工在 Run Detail 中确认通过");
  }

  return (
    <section className="sticky bottom-4 z-20 rounded-2xl border border-black/15 bg-[#fffdf8]/95 p-4 shadow-panel backdrop-blur">
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="font-semibold">人工决策</div>
          <div className="text-xs text-black/45">批准会写入正式正文；拒绝和修订都保留当前不可变版本。</div>
        </div>
        <div className="flex gap-2">
          <button className="btn-soft text-red-700" disabled={disabled || busy} onClick={() => setMode("reject")}>拒绝</button>
          <button className="btn-soft" disabled={disabled || busy} onClick={() => setMode("revise")}>请求修订</button>
          <button className="btn-primary" disabled={disabled || busy} onClick={() => void approve()}>
            {busy ? "处理中..." : "批准并写入正文"}
          </button>
        </div>
      </div>
      {mode && (
        <div className="mt-4 border-t border-black/10 pt-4">
          <label className="label">{mode === "revise" ? "给模型的修订反馈（必填）" : "拒绝原因（可选）"}</label>
          <textarea
            className="field min-h-24"
            value={feedback}
            onChange={(event) => setFeedback(event.target.value)}
            placeholder={mode === "revise" ? "明确指出要保留什么、修改什么，以及验收标准。" : "记录为什么不采用这个版本。"}
          />
          <div className="mt-3 flex justify-end gap-2">
            <button className="btn-soft" onClick={() => setMode(null)}>取消</button>
            <button
              className={mode === "reject" ? "btn bg-red-700 text-white hover:bg-red-800" : "btn-primary"}
              disabled={busy || (mode === "revise" && !feedback.trim())}
              onClick={() => void (mode === "revise" ? onRevise(feedback) : onReject(feedback))}
            >
              确认{mode === "revise" ? "修订" : "拒绝"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
