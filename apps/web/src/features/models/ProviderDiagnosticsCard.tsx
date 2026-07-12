import type { ModelProvider, ProviderTestResult } from "../../types";

interface Props {
  provider: ModelProvider | null;
  result: ProviderTestResult | null;
}

function diagnose(message: string) {
  const text = message.toLowerCase();
  if (text.includes("timeout") || text.includes("timed out")) {
    return ["请求超时", "确认模型已经加载；大模型首次启动可把 timeout 提高到 900-1200 秒。"];
  }
  if (text.includes("connection refused") || text.includes("connect") || text.includes("unreachable")) {
    return ["服务不可达", "确认 LM Studio / llama-server 已启动，并检查 Base URL、端口和 /v1 前缀。"];
  }
  if (text.includes("404") || text.includes("model") && text.includes("not found")) {
    return ["端点或模型名不匹配", "核对服务暴露的 model id；OpenAI-compatible 服务通常需要 /v1。"];
  }
  if (text.includes("401") || text.includes("403") || text.includes("auth") || text.includes("api key")) {
    return ["鉴权失败", "检查 API Key；纯本地服务通常应留空。"];
  }
  return ["Provider 返回错误", "展开原始信息，先核对服务状态、模型 alias 和兼容接口格式。"];
}

export default function ProviderDiagnosticsCard({ provider, result }: Props) {
  if (!result) return null;
  const [category, suggestion] = diagnose(result.message);
  return (
    <section className={`mt-5 rounded-2xl border p-4 ${result.ok ? "border-green-200 bg-green-50" : "border-red-200 bg-red-50"}`}>
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs font-bold uppercase tracking-[0.14em] opacity-55">Provider diagnostics</div>
          <div className="mt-1 font-semibold">{result.ok ? "连接与真实生成成功" : category}</div>
        </div>
        <span className="rounded-full bg-white/60 px-3 py-1 text-xs font-bold">{result.latency_ms} ms</span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
        <div><b>目标：</b>{provider?.base_url || "未保存 Provider"}</div>
        <div><b>模型：</b>{provider?.model || "未保存模型名"}</div>
      </div>
      <p className="mt-3 text-sm">{result.ok ? result.response_preview || result.message : suggestion}</p>
      {!result.ok && (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-semibold">查看原始错误</summary>
          <pre className="mt-2 whitespace-pre-wrap rounded-xl bg-white/60 p-3 text-[10px] leading-5">{result.message}</pre>
        </details>
      )}
    </section>
  );
}
